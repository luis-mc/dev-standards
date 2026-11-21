//! Updater core: the state machine, Ed25519 manifest and SHA-256 checks, the retry timer, the install
//! policies and the audit rows. It follows ../CONTRACT.md. The clock is a fake in test builds.
use ed25519_dalek::{Signature, Verifier, VerifyingKey};
use serde_json::{json, Map, Value};
use sha2::{Digest, Sha256};
use std::io::{Read, Write};
use std::net::TcpStream;

const BACKOFF: [f64; 4] = [60.0, 300.0, 1800.0, 7200.0];
const RETRIES: [f64; 2] = [3600.0, 14400.0];
const DAY: f64 = 86400.0;

#[derive(Clone)]
pub struct Manifest {
    version: String,
    required: bool,
    url: String,
    sha256: String,
}

pub struct Updater {
    pub state: String,
    pub version: String,
    pub paired: bool,
    pub idle: bool,
    pub policy: String,
    pub channel: String,
    pub window: Value,
    pub now: f64,
    pub next_check_at: Option<f64>,
    pub retry_at: Option<f64>,
    pub history: Vec<Value>,
    pub rows: Vec<Value>,
    pub last_check: Option<f64>,
    pub last_result: Option<String>,
    pub selftest_pass: bool,
    server: String,
    pubkey: Option<VerifyingKey>,
    rng: u64,
    offered: Option<Manifest>,
    failures: usize,
    backoff_step: usize,
}

fn semver(v: &str) -> Vec<u64> {
    v.split('.').map(|x| x.parse().unwrap_or(0)).collect()
}

fn hm(s: &str) -> i64 {
    let mut p = s.splitn(2, ':').map(|x| x.parse::<i64>().unwrap_or(0));
    p.next().unwrap_or(0) * 60 + p.next().unwrap_or(0)
}

/// Canonical manifest bytes: sorted keys, compact. serde_json keeps keys sorted (no preserve_order).
fn canonical(m: &Map<String, Value>) -> Vec<u8> {
    serde_json::to_vec(&Value::Object(m.clone())).unwrap_or_default()
}

fn unhex(s: &str) -> Option<Vec<u8>> {
    if s.len() % 2 != 0 || !s.is_ascii() {
        return None;
    }
    (0..s.len()).step_by(2).map(|i| u8::from_str_radix(&s[i..i + 2], 16).ok()).collect()
}

/// A plain HTTP/1.1 GET of a http://host:port/path URL.
fn get(url: &str) -> Result<Vec<u8>, String> {
    let rest = url.strip_prefix("http://").ok_or("only http")?;
    let (host, path) = rest.split_once('/').map(|(h, p)| (h, format!("/{p}"))).unwrap_or((rest, "/".into()));
    let mut s = TcpStream::connect(host).map_err(|e| e.to_string())?;
    s.set_read_timeout(Some(std::time::Duration::from_secs(10))).ok();
    write!(s, "GET {path} HTTP/1.1\r\nHost: {host}\r\nConnection: close\r\n\r\n").map_err(|e| e.to_string())?;
    let mut buf = Vec::new();
    s.read_to_end(&mut buf).map_err(|e| e.to_string())?;
    let split = buf.windows(4).position(|w| w == b"\r\n\r\n").ok_or("bad reply")?;
    let head = String::from_utf8_lossy(&buf[..split]).to_string();
    if !head.starts_with("HTTP/1.1 200") && !head.starts_with("HTTP/1.0 200") {
        return Err(head.lines().next().unwrap_or("").to_string());
    }
    Ok(buf[split + 4..].to_vec())
}

impl Updater {
    pub fn new() -> Self {
        let mut u = Updater {
            state: "unpaired".into(), version: "0.0.0".into(), paired: false, idle: true,
            policy: "automatic_when_idle".into(), channel: "stable".into(), window: Value::Null, now: 0.0,
            next_check_at: None, retry_at: None, history: vec![], rows: vec![], last_check: None,
            last_result: None, selftest_pass: true, server: String::new(), pubkey: None, rng: 1,
            offered: None, failures: 0, backoff_step: 0,
        };
        u.rng = 1;
        u
    }

    /// A small deterministic generator (xorshift) in [0, 1).
    fn rand(&mut self) -> f64 {
        self.rng ^= self.rng << 13;
        self.rng ^= self.rng >> 7;
        self.rng ^= self.rng << 17;
        (self.rng >> 11) as f64 / (1u64 << 53) as f64
    }

    fn go(&mut self, to: &str) {
        self.history.push(json!({"from": self.state, "to": to, "at": self.now}));
        self.state = to.into();
    }

    fn row(&mut self, kind: &str, result: &str, actor: &str, detail: &str, remote: bool) {
        self.rows.push(json!({"at": self.now, "kind": kind, "actor": actor, "result": result, "detail": detail, "remote": remote}));
    }

    fn first_check(&mut self) -> f64 {
        self.now + 60.0 + self.rand() * 540.0
    }

    pub fn reset(&mut self, b: &Value) {
        let mut u = Updater::new();
        u.version = b["version"].as_str().unwrap_or("0.0.0").into();
        u.paired = b["paired"].as_bool().unwrap_or(false);
        u.policy = b["policy"].as_str().unwrap_or("automatic_when_idle").into();
        u.window = b["window"].clone();
        u.channel = b["channel"].as_str().unwrap_or("stable").into();
        u.idle = b["idle"].as_bool().unwrap_or(true);
        u.now = b["now"].as_f64().unwrap_or(0.0);
        u.server = b["server_url"].as_str().unwrap_or("").into();
        u.set_key(b["public_key"].as_str().unwrap_or(""));
        u.rng = (b["seed"].as_u64().unwrap_or(1)).wrapping_mul(0x9E3779B97F4A7C15) | 1;
        if u.paired {
            u.state = "up_to_date".into();
            u.next_check_at = Some(u.first_check());
        }
        *self = u;
    }

    pub fn set_key(&mut self, hex: &str) {
        self.pubkey = unhex(hex).and_then(|v| <[u8; 32]>::try_from(v).ok()).and_then(|k| VerifyingKey::from_bytes(&k).ok());
    }

    pub fn set_server(&mut self, url: &str) {
        self.server = url.into();
    }

    pub fn set_paired(&mut self, p: bool) {
        self.paired = p;
        if p && self.state == "unpaired" {
            self.go("up_to_date");
            self.next_check_at = Some(self.first_check());
        } else if !p {
            self.go("unpaired");
            self.next_check_at = None;
            self.retry_at = None;
        }
    }

    /// Runs one check now. False when unpaired (LC-28).
    pub fn check(&mut self) -> bool {
        if !self.paired {
            return false;
        }
        self.do_check();
        true
    }

    fn in_window(&self, t: f64) -> bool {
        let Some(w) = self.window.as_object() else { return true };
        let m = ((t as i64) % 86400) / 60;
        let (a, z) = (hm(w["start"].as_str().unwrap_or("0:0")), hm(w["end"].as_str().unwrap_or("0:0")));
        if a <= z { a <= m && m < z } else { m >= a || m < z }
    }

    fn window_open(&self) -> Option<f64> {
        let w = self.window.as_object()?;
        if self.state != "waiting" {
            return None;
        }
        let start = (hm(w["start"].as_str()?) * 60) as f64;
        let d = self.now - (self.now as i64 % 86400) as f64;
        [d + start, d + DAY + start].into_iter().find(|t| *t > self.now)
    }

    /// Moves the fake clock and runs every timer that falls due, in order (clock.advance).
    pub fn advance(&mut self, seconds: f64) {
        let target = self.now + seconds;
        loop {
            let mut best: Option<(f64, u8)> = None;
            for (t, k) in [(self.next_check_at, 0u8), (self.retry_at, 1), (self.window_open(), 2)] {
                if let Some(t) = t {
                    if t <= target && best.map_or(true, |(bt, _)| t < bt) {
                        best = Some((t, k));
                    }
                }
            }
            let Some((t, k)) = best else { break };
            if t > self.now {
                self.now = t;
            }
            match k {
                0 => self.do_check(),
                1 => {
                    self.retry_at = None;
                    self.decide();
                }
                _ => self.decide(),
            }
        }
        self.now = target;
    }

    fn parse(&self, raw: &[u8]) -> Result<Manifest, &'static str> {
        let env: Value = serde_json::from_slice(raw).map_err(|_| "bad_signature")?;
        let m = env["manifest"].as_object().ok_or("bad_signature")?;
        let sig = unhex(env["signature"].as_str().unwrap_or("")).and_then(|v| <[u8; 64]>::try_from(v).ok()).ok_or("bad_signature")?;
        let key = self.pubkey.as_ref().ok_or("bad_signature")?;
        key.verify(&canonical(m), &Signature::from_bytes(&sig)).map_err(|_| "bad_signature")?;
        let s = |k: &str| m.get(k).and_then(Value::as_str).unwrap_or("").to_string();
        let out = Manifest { version: s("version"), required: m["required"].as_bool().unwrap_or(false), url: s("url"), sha256: s("sha256") };
        if m["expires_at"].as_f64().unwrap_or(0.0) <= self.now {
            return Err("expired");
        }
        if semver(&out.version) < semver(&self.version) {
            return Err("older_version");
        }
        Ok(out)
    }

    fn do_check(&mut self) {
        self.last_check = Some(self.now);
        let raw = match get(&format!("{}/{}/manifest.json", self.server, self.channel)) {
            Ok(r) => r,
            Err(_) => {
                self.next_check_at = Some(self.now + BACKOFF[self.backoff_step.min(3)]);
                self.backoff_step += 1;
                self.last_result = Some("failed".into());
                self.row("check", "failed", "updater", "", false);
                return;
            }
        };
        self.backoff_step = 0;
        let jitter = 0.8 + 0.4 * self.rand();
        self.next_check_at = Some(self.now + 21600.0 * jitter);
        self.row("check", "ok", "updater", "", false);
        let m = match self.parse(&raw) {
            Ok(m) => m,
            Err(why) => return self.refuse(why),
        };
        if m.version == self.version {
            self.last_result = Some("up_to_date".into());
            return self.go("up_to_date");
        }
        let same = self.offered.as_ref().map_or(false, |o| o.version == m.version);
        if same && self.state == "skipped" {
            return;
        }
        if same && self.state == "rolled_back" && self.retry_at.is_some() {
            return;
        }
        if !same {
            self.failures = 0;
            self.retry_at = None;
        }
        self.offered = Some(m);
        self.last_result = Some("available".into());
        self.go("available");
        self.decide();
    }

    fn refuse(&mut self, reason: &str) {
        self.go("refused");
        self.last_result = Some("refused".into());
        self.row("refused", "refused", "updater", reason, false);
    }

    /// Applies the policy to the offered version (LC-6).
    fn decide(&mut self) {
        let Some(m) = self.offered.clone() else { return };
        if m.required {
            self.download("updater", false);
        } else if self.policy == "ask_first" {
            self.go("review");
        } else if self.idle && self.in_window(self.now) {
            self.download("updater", false);
        } else {
            self.go("waiting");
        }
    }

    pub fn reeval(&mut self) {
        if self.state == "waiting" {
            self.decide();
        }
    }

    /// Starts an install by a click or by a remote owner (LC-25).
    pub fn install(&mut self, actor: &str, remote: bool, click: bool) {
        if ["review", "waiting", "available"].contains(&self.state.as_str()) && self.offered.is_some() && (click || remote) {
            self.download(actor, remote);
        }
    }

    fn download(&mut self, actor: &str, remote: bool) {
        let Some(m) = self.offered.clone() else { return };
        self.go("downloading");
        let Ok(data) = get(&m.url) else { return self.refuse("download_failed") };
        self.go("verifying");
        let sum: String = Sha256::digest(&data).iter().map(|b| format!("{b:02x}")).collect();
        if sum != m.sha256 {
            return self.refuse("bad_hash");
        }
        self.go("installing");
        self.go("testing");
        if self.selftest_pass {
            self.version = m.version.clone();
            self.go("updated");
            self.last_result = Some("updated".into());
            self.row("install", "ok", actor, "", remote);
            self.offered = None;
            return;
        }
        self.go("rolling_back");
        self.go("rolled_back");
        self.last_result = Some("rolled_back".into());
        self.row("install", "rolled_back", actor, "", remote);
        self.row("rollback", "ok", actor, "", remote);
        self.failures += 1;
        if self.failures >= 3 {
            self.row("skip", "ok", "updater", &m.version, false);
            return self.go("skipped");
        }
        self.retry_at = Some(self.now + RETRIES[self.failures - 1]);
    }

    pub fn view(&self) -> Value {
        json!({"state": self.state, "version": self.version, "paired": self.paired, "policy": self.policy,
               "window": self.window, "channel": self.channel, "idle": self.idle, "now": self.now,
               "next_check_at": self.next_check_at, "retry_at": self.retry_at, "history": self.history})
    }

    /// One test-interface call. `verb` and `body` are those of ../CONTRACT.md.
    pub fn call(&mut self, verb: &str, b: &Value) -> Value {
        match verb {
            "reset" => self.reset(b),
            "server.set" => {
                self.set_server(b["server_url"].as_str().unwrap_or(""));
                self.set_key(b["public_key"].as_str().unwrap_or(""));
            }
            "clock.set" => self.now = b["now"].as_f64().unwrap_or(self.now),
            "clock.advance" => self.advance(b["seconds"].as_f64().unwrap_or(0.0)),
            "idle.set" => {
                self.idle = b["idle"].as_bool().unwrap_or(true);
                self.reeval();
            }
            "policy.set" => {
                self.policy = b["policy"].as_str().unwrap_or("automatic_when_idle").into();
                self.window = b["window"].clone();
                self.reeval();
            }
            "selftest.set" => self.selftest_pass = b["pass"].as_bool().unwrap_or(true), // gitleaks:allow secret-scan:ignore (self-test result flag, not a secret)
            "pair" => self.set_paired(b["paired"].as_bool().unwrap_or(false)),
            "install" => self.install(b["actor"].as_str().unwrap_or(""), b["remote"].as_bool().unwrap_or(false), b["click"].as_bool().unwrap_or(false)),
            "check" => {
                let ran = self.check();
                return json!({"ran": ran, "state": self.view()});
            }
            "audit" => return json!({"rows": self.rows}),
            "settings" => return json!({"policy": self.policy, "window": self.window, "channel": self.channel, "last_check": self.last_check, "last_result": self.last_result}),
            "state" => {}
            _ => return json!({"error": format!("unknown verb {verb}")}),
        }
        self.view()
    }
}

impl Default for Updater {
    fn default() -> Self {
        Self::new()
    }
}
