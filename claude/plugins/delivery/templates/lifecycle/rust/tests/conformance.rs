//! Runs the shared conformance runner against the test server. LIFECYCLE_CONFORMANCE is the runner's path.
use std::io::{BufRead, BufReader};
use std::process::{Command, Stdio};

#[test]
fn passes_the_runner() {
    let Ok(runner) = std::env::var("LIFECYCLE_CONFORMANCE") else {
        eprintln!("LIFECYCLE_CONFORMANCE is not set; skipped");
        return;
    };
    let py = std::env::var("PYTHON").unwrap_or_else(|_| "python3".into());
    let mut srv = Command::new(env!("CARGO_BIN_EXE_updater-test-server")).stdout(Stdio::piped()).spawn().unwrap();
    let mut addr = String::new();
    BufReader::new(srv.stdout.take().unwrap()).read_line(&mut addr).unwrap();
    let out = Command::new(py).args([&runner, "--url", &format!("http://{}", addr.trim())]).output().unwrap();
    srv.kill().ok();
    println!("{}", String::from_utf8_lossy(&out.stdout));
    assert!(out.status.success(), "runner failed:\n{}{}", String::from_utf8_lossy(&out.stdout), String::from_utf8_lossy(&out.stderr));
}
