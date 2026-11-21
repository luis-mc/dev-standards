//! Test-build server for the test interface: `updater-test-server [addr]` prints the address it listens on.
use serde_json::Value;
use std::io::{BufRead, BufReader, Read, Write};
use std::net::TcpListener;
use updater_core::Updater;

fn main() {
    let addr = std::env::args().nth(1).unwrap_or_else(|| "127.0.0.1:0".into());
    let l = TcpListener::bind(&addr).expect("bind");
    println!("{}", l.local_addr().unwrap());
    std::io::stdout().flush().ok();
    let mut u = Updater::new();
    for conn in l.incoming().flatten() {
        let mut r = BufReader::new(conn.try_clone().unwrap());
        let mut line = String::new();
        if r.read_line(&mut line).is_err() {
            continue;
        }
        let path = line.split_whitespace().nth(1).unwrap_or("").to_string();
        let mut len = 0usize;
        loop {
            let mut h = String::new();
            if r.read_line(&mut h).unwrap_or(0) == 0 || h.trim().is_empty() {
                break;
            }
            if let Some(v) = h.to_ascii_lowercase().strip_prefix("content-length:") {
                len = v.trim().parse().unwrap_or(0);
            }
        }
        let mut body = vec![0u8; len];
        r.read_exact(&mut body).ok();
        let b: Value = serde_json::from_slice(&body).unwrap_or(Value::Null);
        let out = u.call(path.trim_start_matches("/test/"), &b).to_string();
        let mut c = conn;
        write!(c, "HTTP/1.1 200 OK\r\nContent-Type: application/json\r\nContent-Length: {}\r\nConnection: close\r\n\r\n{}", out.len(), out).ok();
    }
}
