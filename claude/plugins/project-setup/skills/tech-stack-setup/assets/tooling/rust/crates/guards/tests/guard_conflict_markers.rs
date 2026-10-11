//! STACKSPEC 13.5 guard test (starter): no source file may contain a
//! merge-conflict marker line.
//!
//! Markers left in a committed file break the build in some languages and
//! silently change behaviour in config and data files. The branch gate and the
//! pre-push hook run every `guard_*` test on every push, whatever changed.
//!
//! Markdown and plain text are excluded: seven `=` alone on a line is a setext
//! heading underline there, not a conflict.

use std::fs;
use std::path::{Path, PathBuf};

const SCANNED: &[&str] = &[
    "rs", "toml", "lock", "json", "yml", "yaml", "sql", "sh", "ts", "tsx", "js", "css", "html",
];
const SKIP_DIRS: &[&str] = &[".git", "target", "node_modules", "vendor", ".delivery"];

/// Built from pieces so this file does not contain a marker line itself.
fn is_marker(line: &str) -> bool {
    let start = "<".repeat(7);
    let sep = "=".repeat(7);
    let end = ">".repeat(7);
    let opens = |m: &str| line == m || line.starts_with(&format!("{m} "));
    opens(&start) || line == sep || opens(&end)
}

/// The nearest ancestor holding `.git`, else the outermost one holding a
/// `Cargo.lock` (a source tarball has no `.git`).
fn repository_root() -> PathBuf {
    let start = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let mut outermost_lock = None;
    for dir in start.ancestors() {
        if dir.join(".git").exists() {
            return dir.to_path_buf();
        }
        if dir.join("Cargo.lock").is_file() {
            outermost_lock = Some(dir.to_path_buf());
        }
    }
    outermost_lock.unwrap_or(start)
}

fn walk(dir: &Path, out: &mut Vec<PathBuf>) {
    let Ok(entries) = fs::read_dir(dir) else { return };
    for entry in entries.flatten() {
        let path = entry.path();
        let name = entry.file_name().to_string_lossy().into_owned();
        if path.is_dir() {
            // A directory with its own `.git` is another checkout (an agent's
            // worktree under .claude/worktrees, a submodule): its files are in
            // whatever state that work is in right now, mid-merge included.
            if !SKIP_DIRS.contains(&name.as_str()) && !path.join(".git").exists() {
                walk(&path, out);
            }
        } else if path
            .extension()
            .and_then(|e| e.to_str())
            .is_some_and(|e| SCANNED.contains(&e.to_ascii_lowercase().as_str()))
        {
            out.push(path);
        }
    }
}

#[test]
fn guard_no_conflict_markers() {
    let root = repository_root();
    let mut files = Vec::new();
    walk(&root, &mut files);
    assert!(
        !files.is_empty(),
        "scanned no files under {}; an empty scan would pass for the wrong reason",
        root.display()
    );

    let mut hits = Vec::new();
    for file in &files {
        let Ok(text) = fs::read_to_string(file) else { continue }; // not UTF-8: not source
        for (i, line) in text.lines().enumerate() {
            if is_marker(line) {
                let rel = file.strip_prefix(&root).unwrap_or(file);
                // '/' on every OS, so the report reads the same on Windows.
                let rel = rel.to_string_lossy().replace('\\', "/");
                hits.push(format!("{}:{}: {}", rel, i + 1, line));
            }
        }
    }
    assert!(hits.is_empty(), "merge-conflict markers found:\n{}", hits.join("\n"));
}
