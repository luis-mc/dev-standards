//! Words lint (DS235a, LC-2 and LC-31). Copy to `tests/words_lint.rs` of the crate (an integration test), set
//! `LIFECYCLE_FILES`, and run `cargo test --test words_lint`. Standard library only.
//!
//! LC-2: every lifecycle UI string is a value of the words table in docs/design-system/vN/lifecycle.json, and no
//! banned word is in it. LC-31: notices are plain: no error code, no HTTP status, no doubled punctuation.

use std::collections::HashSet;
use std::fs;
use std::path::{Path, PathBuf};

/// Files and folders that hold lifecycle UI strings, relative to the crate root.
const LIFECYCLE_FILES: &[&str] = &["src/lifecycle"];

const DEFAULT_BANNED: &[&str] = &["OK", "Yes", "No", "Install now", "Later", "daemon", "binary", "payload"];
const CASE_SENSITIVE: &[&str] = &["OK", "Yes", "No", "Later"];

#[derive(Debug)]
#[allow(dead_code)]
struct Finding {
    rule: &'static str,
    text: String,
    why: String,
}

fn is_alnum(c: char) -> bool {
    c.is_ascii_alphanumeric()
}

/// `needle` in `text` with no letter or digit on either side.
fn whole_word(text: &str, needle: &str) -> bool {
    let mut from = 0;
    while let Some(i) = text[from..].find(needle) {
        let s = from + i;
        let e = s + needle.len();
        let before = text[..s].chars().next_back().map_or(false, is_alnum);
        let after = text[e..].chars().next().map_or(false, is_alnum);
        if !before && !after {
            return true;
        }
        from = s + needle.chars().next().map_or(1, |c| c.len_utf8());
    }
    false
}

fn banned_hits(text: &str, banned: &[String]) -> Vec<String> {
    banned
        .iter()
        .filter(|w| {
            if CASE_SENSITIVE.contains(&w.as_str()) {
                whole_word(text, w)
            } else {
                whole_word(&text.to_lowercase(), &w.to_lowercase())
            }
        })
        .cloned()
        .collect()
}

fn digits_at(b: &[u8], i: usize, n: usize) -> bool {
    i + n <= b.len() && b[i..i + n].iter().all(|c| c.is_ascii_digit())
}

fn skip_space(b: &[u8], mut i: usize) -> usize {
    while i < b.len() && b[i].is_ascii_whitespace() {
        i += 1;
    }
    i
}

fn has_error_code(text: &str) -> bool {
    let b = text.as_bytes();
    let lower = text.to_lowercase();
    let lb = lower.as_bytes();
    // 0x followed by a hex digit
    for i in 0..b.len().saturating_sub(2) {
        if b[i] == b'0' && b[i + 1] == b'x' && b[i + 2].is_ascii_hexdigit() {
            return true;
        }
    }
    // "error" or "code", spaces, a digit
    for word in ["error", "code"] {
        let mut from = 0;
        while let Some(i) = lower[from..].find(word) {
            let s = from + i;
            let j = s + word.len();
            let k = skip_space(lb, j);
            if k > j && k < lb.len() && lb[k].is_ascii_digit() && (s == 0 || !is_alnum(b[s - 1] as char)) {
                return true;
            }
            from = s + 1;
        }
    }
    // a token: 1 to 5 capitals, optional - or _, three or more digits (E1603, ERR_404)
    for tok in text.split(|c: char| !(c.is_ascii_alphanumeric() || c == '-' || c == '_')) {
        let t = tok.as_bytes();
        let caps = t.iter().take_while(|c| c.is_ascii_uppercase()).count();
        if !(1..=5).contains(&caps) {
            continue;
        }
        let mut i = caps;
        if i < t.len() && (t[i] == b'-' || t[i] == b'_') {
            i += 1;
        }
        if i + 3 <= t.len() && t[i..].iter().all(|c| c.is_ascii_digit()) {
            return true;
        }
    }
    false
}

fn has_http_status(text: &str) -> bool {
    let lower = text.to_lowercase();
    let b = lower.as_bytes();
    let status3 = |i: usize| digits_at(b, i, 3) && (b'1'..=b'5').contains(&b[i]) && !b.get(i + 3).map_or(false, |c| c.is_ascii_digit());
    let mut from = 0;
    while let Some(i) = lower[from..].find("http") {
        let s = from + i + 4;
        if status3(skip_space(b, s)) {
            return true;
        }
        from = s;
    }
    from = 0;
    while let Some(i) = lower[from..].find("status") {
        let mut s = skip_space(b, from + i + 6);
        if lower[s..].starts_with("code") {
            s = skip_space(b, s + 4);
        }
        if s > from + i + 6 && status3(s) {
            return true;
        }
        from += i + 6;
    }
    false
}

fn plain_hits(text: &str) -> Vec<&'static str> {
    let mut out = vec![];
    if has_error_code(text) {
        out.push("error code");
    }
    if has_http_status(text) {
        out.push("HTTP status");
    }
    let cs: Vec<char> = text.chars().collect();
    if cs.windows(2).any(|w| w[0] == w[1] && ".,;:!?".contains(w[0])) {
        out.push("doubled punctuation");
    }
    out
}

/// Every JSON string token of `text` (keys and values; a superset of the table values).
fn json_strings(text: &str) -> Vec<String> {
    let mut out = vec![];
    let mut cur = String::new();
    let (mut inside, mut esc) = (false, false);
    for c in text.chars() {
        if inside {
            if esc {
                cur.push(c);
                esc = false;
            } else if c == '\\' {
                esc = true;
            } else if c == '"' {
                out.push(std::mem::take(&mut cur));
                inside = false;
            } else {
                cur.push(c);
            }
        } else if c == '"' {
            inside = true;
        }
    }
    out
}

/// The text of the `"words"` object of a lifecycle.json.
fn words_section(text: &str) -> Option<&str> {
    let start = text.find("\"words\"")?;
    let open = start + text[start..].find('{')?;
    let (mut depth, mut inside) = (0, false);
    for (i, c) in text[open..].char_indices() {
        match c {
            '"' => inside = !inside,
            '{' if !inside => depth += 1,
            '}' if !inside => {
                depth -= 1;
                if depth == 0 {
                    return Some(&text[open..open + i + 1]);
                }
            }
            _ => {}
        }
    }
    None
}

/// The string literals of Rust source: "..." (raw strings are not read).
fn literals(src: &str) -> Vec<String> {
    let mut out = vec![];
    let mut cur = String::new();
    let (mut inside, mut esc) = (false, false);
    for c in src.chars() {
        if inside {
            if esc {
                cur.push(match c { 'n' => '\n', 't' => '\t', o => o });
                esc = false;
            } else if c == '\\' {
                esc = true;
            } else if c == '"' {
                out.push(std::mem::take(&mut cur));
                inside = false;
            } else {
                cur.push(c);
            }
        } else if c == '"' {
            inside = true;
        }
    }
    out
}

fn check_strings(strs: &[String], words_json: &str) -> Vec<Finding> {
    let tokens = json_strings(words_section(words_json).unwrap_or(""));
    let allowed: HashSet<&String> = tokens.iter().collect();
    let mut banned: Vec<String> = DEFAULT_BANNED.iter().map(|s| s.to_string()).collect();
    if let Some(i) = tokens.iter().position(|t| t == "banned") {
        // the banned list is the first array after the key; its entries are the strings up to "states"
        banned.extend(tokens[i + 1..].iter().take_while(|t| *t != "states").cloned());
    }
    let mut found = vec![];
    for s in strs {
        if !s.chars().any(|c| c.is_ascii_alphabetic()) {
            continue;
        }
        for w in banned_hits(s, &banned) {
            found.push(Finding { rule: "LC-2", text: s.clone(), why: format!("banned word '{w}'") });
        }
        if !allowed.contains(s) {
            found.push(Finding { rule: "LC-2", text: s.clone(), why: "not in the words table".into() });
        }
        for why in plain_hits(s) {
            found.push(Finding { rule: "LC-31", text: s.clone(), why: why.into() });
        }
    }
    found
}

fn find_lifecycle(root: &Path) -> Option<PathBuf> {
    let dir = root.join("docs").join("design-system");
    let mut nums: Vec<u32> = fs::read_dir(&dir)
        .ok()?
        .filter_map(|e| e.ok()?.file_name().to_str()?.strip_prefix('v')?.parse().ok())
        .filter(|n| *n > 0)
        .collect();
    nums.sort_by(|a, b| b.cmp(a));
    let mut names: Vec<String> = nums.iter().map(|n| format!("v{n}")).collect();
    names.push("next-version".into());
    names.into_iter().map(|n| dir.join(n).join("lifecycle.json")).find(|p| p.is_file())
}

fn rust_files(path: &Path, out: &mut Vec<PathBuf>) {
    if path.is_file() {
        out.push(path.to_path_buf());
    } else if let Ok(rd) = fs::read_dir(path) {
        for e in rd.flatten() {
            rust_files(&e.path(), out);
        }
    }
}

fn scan_root(root: &Path) -> Vec<Finding> {
    let lc = find_lifecycle(root).expect("no lifecycle.json under docs/design-system");
    let words = fs::read_to_string(lc).unwrap();
    let mut files = vec![];
    for f in LIFECYCLE_FILES {
        rust_files(&root.join(f), &mut files);
    }
    files
        .iter()
        .filter(|p| p.extension().map_or(false, |x| x == "rs"))
        .flat_map(|p| check_strings(&literals(&fs::read_to_string(p).unwrap()), &words))
        .collect()
}

#[cfg(test)]
mod tests {
    use super::*;

    const WORDS: &str = r#"{"schema":"1","words":{"banned":["OK"],"states":{"available":{"title":"Version {version} is ready."}}}}"#;

    fn banned() -> Vec<String> {
        DEFAULT_BANNED.iter().map(|s| s.to_string()).collect()
    }

    #[test]
    fn clean_string_passes() {
        assert!(check_strings(&["Version {version} is ready.".to_string()], WORDS).is_empty());
    }

    #[test]
    fn each_banned_word_is_flagged() {
        for w in DEFAULT_BANNED {
            assert!(!banned_hits(&format!("Press {w} to go"), &banned()).is_empty(), "{w}");
        }
        assert!(banned_hits("Nothing changed. Notes.", &banned()).is_empty());
    }

    #[test]
    fn notices_are_plain() {
        assert!(plain_hits("Failed with 0x80070005").contains(&"error code"));
        assert!(plain_hits("Error 1603").contains(&"error code"));
        assert!(plain_hits("It said E1603").contains(&"error code"));
        assert!(plain_hits("The server said HTTP 503").contains(&"HTTP status"));
        assert!(plain_hits("Done..").contains(&"doubled punctuation"));
        assert!(plain_hits("Nothing changed. 500 MB free.").is_empty());
    }

    #[test]
    fn string_not_in_table_is_flagged() {
        let f = check_strings(&["Click here".to_string()], WORDS);
        assert_eq!(f.len(), 1);
        assert_eq!(f[0].why, "not in the words table");
    }

    #[test]
    fn reads_literals() {
        assert_eq!(literals("let a = \"x y\"; let b = \"z\\\"w\";"), vec!["x y", "z\"w"]);
    }

    #[test]
    fn project_has_no_finding() {
        let root = Path::new(env!("CARGO_MANIFEST_DIR"));
        let f = scan_root(root);
        assert!(f.is_empty(), "{f:?}");
    }
}
