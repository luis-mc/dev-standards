// Package updatercore is an updater core: the state machine, Ed25519 manifest and SHA-256 checks,
// the retry timer, the install policies and the audit rows. It follows ../CONTRACT.md.
// The clock is a fake in test builds: nothing here reads the wall clock.
package updatercore

import (
	"bytes"
	"crypto/ed25519"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"math/rand"
	"net/http"
	"strconv"
	"strings"
	"time"
)

const day = 86400.0

var (
	backoff = []float64{60, 300, 1800, 7200} // failed-check backoff
	retries = []float64{3600, 14400}         // retry after a rollback
)

// Window is a daily install window in UTC, "HH:MM".
type Window struct {
	Start string `json:"start"`
	End   string `json:"end"`
}

// Move is one entry of the state history.
type Move struct {
	From string  `json:"from"`
	To   string  `json:"to"`
	At   float64 `json:"at"`
}

// Row is one audit row.
type Row struct {
	At     float64 `json:"at"`
	Kind   string  `json:"kind"`
	Actor  string  `json:"actor"`
	Result string  `json:"result"`
	Detail string  `json:"detail"`
	Remote bool    `json:"remote"`
}

type manifest struct {
	Version   string
	Required  bool
	ExpiresAt float64
	URL       string
	SHA256    string
}

// Updater holds all state. It is not safe for concurrent use; the test interface serialises calls.
type Updater struct {
	State, Version        string
	Paired, Idle          bool
	Policy, Channel       string
	Window                *Window
	Now                   float64
	NextCheckAt, RetryAt  *float64
	History               []Move
	Rows                  []Row
	LastCheck             *float64
	LastResult            *string
	SelfTestPass          bool
	server                string
	pub                   ed25519.PublicKey
	rng                   *rand.Rand
	offered               *manifest
	failures, backoffStep int
}

func ptr(f float64) *float64 { return &f }

func (u *Updater) go_(to string) {
	u.History = append(u.History, Move{u.State, to, u.Now})
	u.State = to
}

func (u *Updater) row(kind, result, actor, detail string, remote bool) {
	u.Rows = append(u.Rows, Row{u.Now, kind, actor, result, detail, remote})
}

func (u *Updater) result(s string) { u.LastResult = &s }

func (u *Updater) firstCheck() *float64 { return ptr(u.Now + 60 + u.rng.Float64()*540) }

// Reset starts a fresh updater (test builds only).
func (u *Updater) Reset(version string, paired bool, policy string, w *Window, channel string, idle bool, now float64, server string, pub ed25519.PublicKey, seed int64) {
	*u = Updater{Version: version, Paired: paired, Policy: policy, Window: w, Channel: channel, Idle: idle, Now: now,
		server: server, pub: pub, rng: rand.New(rand.NewSource(seed)), SelfTestPass: true, History: []Move{}, Rows: []Row{}}
	u.State = "unpaired"
	if paired {
		u.State = "up_to_date"
		u.NextCheckAt = u.firstCheck()
	}
}

func (u *Updater) SetPaired(p bool) {
	u.Paired = p
	switch {
	case p && u.State == "unpaired":
		u.go_("up_to_date")
		u.NextCheckAt = u.firstCheck()
	case !p:
		u.go_("unpaired")
		u.NextCheckAt, u.RetryAt = nil, nil
	}
}

// Check runs one check now. It reports false when unpaired (LC-28).
func (u *Updater) Check() bool {
	if !u.Paired {
		return false
	}
	u.doCheck()
	return true
}

func (u *Updater) inWindow(t float64) bool {
	if u.Window == nil {
		return true
	}
	m := int(int64(t)%86400) / 60
	a, z := hm(u.Window.Start), hm(u.Window.End)
	if a <= z {
		return a <= m && m < z
	}
	return m >= a || m < z
}

func hm(s string) int {
	p := strings.SplitN(s, ":", 2)
	h, _ := strconv.Atoi(p[0])
	m, _ := strconv.Atoi(p[1])
	return h*60 + m
}

func (u *Updater) windowOpen() *float64 {
	if u.State != "waiting" || u.Window == nil {
		return nil
	}
	start := float64(hm(u.Window.Start) * 60)
	d := u.Now - float64(int64(u.Now)%86400)
	for _, t := range []float64{d + start, d + day + start} {
		if t > u.Now {
			return ptr(t)
		}
	}
	return nil
}

// Advance moves the fake clock and runs every timer that falls due, in order (the contract's clock.advance).
func (u *Updater) Advance(seconds float64) {
	target := u.Now + seconds
	for {
		kind, at := "", 0.0
		for _, c := range []struct {
			k string
			t *float64
		}{{"check", u.NextCheckAt}, {"retry", u.RetryAt}, {"window", u.windowOpen()}} {
			if c.t != nil && *c.t <= target && (kind == "" || *c.t < at) {
				kind, at = c.k, *c.t
			}
		}
		if kind == "" {
			break
		}
		if at > u.Now {
			u.Now = at
		}
		switch kind {
		case "check":
			u.doCheck()
		case "retry":
			u.RetryAt = nil
			u.decide()
		default:
			u.decide()
		}
	}
	u.Now = target
}

func get(url string) ([]byte, error) {
	c := http.Client{Timeout: 10 * time.Second}
	r, err := c.Get(url)
	if err != nil {
		return nil, err
	}
	defer r.Body.Close()
	if r.StatusCode != 200 {
		return nil, fmt.Errorf("status %d", r.StatusCode)
	}
	return io.ReadAll(r.Body)
}

// canonical is the signed form: sorted keys, compact separators. Manifests are ASCII.
func canonical(m map[string]interface{}) ([]byte, error) {
	var b bytes.Buffer
	e := json.NewEncoder(&b)
	e.SetEscapeHTML(false)
	if err := e.Encode(m); err != nil {
		return nil, err
	}
	return bytes.TrimRight(b.Bytes(), "\n"), nil
}

func vless(a, b string) bool {
	pa, pb := strings.Split(a, "."), strings.Split(b, ".")
	for i := 0; i < len(pa) && i < len(pb); i++ {
		x, _ := strconv.Atoi(pa[i])
		y, _ := strconv.Atoi(pb[i])
		if x != y {
			return x < y
		}
	}
	return len(pa) < len(pb)
}

// parse verifies the signed manifest and returns it, or an error code from the contract.
func (u *Updater) parse(raw []byte) (*manifest, string) {
	var env struct {
		Manifest  map[string]interface{} `json:"manifest"`
		Signature string                 `json:"signature"`
	}
	dec := json.NewDecoder(bytes.NewReader(raw))
	dec.UseNumber()
	if err := dec.Decode(&env); err != nil || env.Manifest == nil {
		return nil, "bad_signature"
	}
	sig, err := hex.DecodeString(env.Signature)
	body, err2 := canonical(env.Manifest)
	if err != nil || err2 != nil || len(sig) != ed25519.SignatureSize || !ed25519.Verify(u.pub, body, sig) {
		return nil, "bad_signature"
	}
	str := func(k string) string { s, _ := env.Manifest[k].(string); return s }
	exp, _ := env.Manifest["expires_at"].(json.Number).Float64()
	req, _ := env.Manifest["required"].(bool)
	m := &manifest{str("version"), req, exp, str("url"), str("sha256")}
	if m.ExpiresAt <= u.Now {
		return nil, "expired"
	}
	if vless(m.Version, u.Version) {
		return nil, "older_version"
	}
	return m, ""
}

func (u *Updater) doCheck() {
	u.LastCheck = ptr(u.Now)
	raw, err := get(fmt.Sprintf("%s/%s/manifest.json", u.server, u.Channel))
	if err != nil {
		step := u.backoffStep
		if step > 3 {
			step = 3
		}
		u.NextCheckAt = ptr(u.Now + backoff[step])
		u.backoffStep++
		u.result("failed")
		u.row("check", "failed", "updater", "", false)
		return
	}
	u.backoffStep = 0
	u.NextCheckAt = ptr(u.Now + 21600*(0.8+0.4*u.rng.Float64()))
	u.row("check", "ok", "updater", "", false)
	m, bad := u.parse(raw)
	if bad != "" {
		u.refuse(bad)
		return
	}
	if m.Version == u.Version {
		u.result("up_to_date")
		u.go_("up_to_date")
		return
	}
	same := u.offered != nil && u.offered.Version == m.Version
	if same && u.State == "skipped" {
		return
	}
	if same && u.State == "rolled_back" && u.RetryAt != nil {
		return
	}
	if !same {
		u.failures, u.RetryAt = 0, nil
	}
	u.offered = m
	u.result("available")
	u.go_("available")
	u.decide()
}

func (u *Updater) refuse(reason string) {
	u.go_("refused")
	u.result("refused")
	u.row("refused", "refused", "updater", reason, false)
}

// decide applies the policy to the offered version (LC-6).
func (u *Updater) decide() {
	switch {
	case u.offered.Required:
		u.download("updater", false)
	case u.Policy == "ask_first":
		u.go_("review")
	case u.Idle && u.inWindow(u.Now):
		u.download("updater", false)
	default:
		u.go_("waiting")
	}
}

// Reeval runs the policy again after idle, policy or pairing changed.
func (u *Updater) Reeval() {
	if u.State == "waiting" && u.offered != nil {
		u.decide()
	}
}

// Install starts an install by a click or by a remote owner (LC-25).
func (u *Updater) Install(actor string, remote, click bool) {
	switch u.State {
	case "review", "waiting", "available":
		if u.offered != nil && (click || remote) {
			u.download(actor, remote)
		}
	}
}

func (u *Updater) download(actor string, remote bool) {
	m := u.offered
	u.go_("downloading")
	data, err := get(m.URL)
	if err != nil {
		u.refuse("download_failed")
		return
	}
	u.go_("verifying")
	sum := sha256.Sum256(data)
	if hex.EncodeToString(sum[:]) != m.SHA256 {
		u.refuse("bad_hash")
		return
	}
	u.go_("installing")
	u.go_("testing")
	if u.SelfTestPass {
		u.Version = m.Version
		u.go_("updated")
		u.result("updated")
		u.row("install", "ok", actor, "", remote)
		u.offered = nil
		return
	}
	u.go_("rolling_back")
	u.go_("rolled_back")
	u.result("rolled_back")
	u.row("install", "rolled_back", actor, "", remote)
	u.row("rollback", "ok", actor, "", remote)
	u.failures++
	if u.failures >= 3 {
		u.row("skip", "ok", "updater", m.Version, false)
		u.go_("skipped")
		return
	}
	u.RetryAt = ptr(u.Now + retries[u.failures-1])
}

var ErrBadKey = errors.New("bad public key")
