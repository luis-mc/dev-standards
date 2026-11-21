// Words lint (DS235a, LC-2 and LC-31). Copy into a package of its own (for example internal/wordslint) with
// words_lint_test.go, and set Config. Standard library only.
//
// LC-2: every lifecycle UI string is a value of the words table in docs/design-system/vN/lifecycle.json, and no
// banned word is in it. LC-31: notices are plain: no error code, no HTTP status, no doubled punctuation.
package wordslint

import (
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"
)

// Config: files and folders that hold lifecycle UI strings, relative to the repo root.
var Config = struct {
	LifecycleFiles []string
}{LifecycleFiles: []string{"internal/lifecycle"}}

var DefaultBanned = []string{"OK", "Yes", "No", "Install now", "Later", "daemon", "binary", "payload"}

var caseSensitive = map[string]bool{"OK": true, "Yes": true, "No": true, "Later": true}

type Finding struct{ Rule, Text, Why string }

type Words struct {
	Banned []string                     `json:"banned"`
	States map[string]map[string]string `json:"states"`
}

func isAlnum(b byte) bool {
	return b >= '0' && b <= '9' || b >= 'a' && b <= 'z' || b >= 'A' && b <= 'Z'
}

// wholeWord reports whether needle is in text with no letter or digit on either side.
func wholeWord(text, needle string) bool {
	for i := 0; i+len(needle) <= len(text); i++ {
		if text[i:i+len(needle)] != needle {
			continue
		}
		if i > 0 && isAlnum(text[i-1]) {
			continue
		}
		if e := i + len(needle); e < len(text) && isAlnum(text[e]) {
			continue
		}
		return true
	}
	return false
}

func BannedHits(text string, banned []string) []string {
	var out []string
	for _, w := range banned {
		t, n := text, w
		if !caseSensitive[w] {
			t, n = strings.ToLower(text), strings.ToLower(w)
		}
		if wholeWord(t, n) {
			out = append(out, w)
		}
	}
	return out
}

var (
	hexCode = regexp.MustCompile(`0x[0-9a-fA-F]`)
	errWord = regexp.MustCompile(`(?i)\b(?:error|code)\s+[0-9]`)
	httpSt  = regexp.MustCompile(`(?i)HTTP\s*[1-5][0-9]{2}\b|\bstatus(?:\s+code)?\s+[1-5][0-9]{2}\b`)
	tokOnly = regexp.MustCompile(`^[A-Z]{1,5}[-_]?[0-9]{3,}$`)
)

func hasErrorCode(text string) bool {
	if hexCode.MatchString(text) || errWord.MatchString(text) {
		return true
	}
	for _, tok := range strings.FieldsFunc(text, func(r rune) bool {
		return !(r >= '0' && r <= '9' || r >= 'a' && r <= 'z' || r >= 'A' && r <= 'Z' || r == '-' || r == '_')
	}) {
		if tokOnly.MatchString(tok) {
			return true
		}
	}
	return false
}

func PlainHits(text string) []string {
	var out []string
	if hasErrorCode(text) {
		out = append(out, "error code")
	}
	if httpSt.MatchString(text) {
		out = append(out, "HTTP status")
	}
	for i := 1; i < len(text); i++ {
		if text[i] == text[i-1] && strings.IndexByte(".,;:!?", text[i]) >= 0 {
			out = append(out, "doubled punctuation")
			break
		}
	}
	return out
}

func (w Words) tableValues() map[string]bool {
	out := map[string]bool{}
	for _, st := range w.States {
		for _, v := range st {
			out[v] = true
		}
	}
	return out
}

var letter = regexp.MustCompile(`[A-Za-z]`)

func CheckStrings(strs []string, w Words) []Finding {
	allowed := w.tableValues()
	banned := append(append([]string{}, DefaultBanned...), w.Banned...)
	var found []Finding
	for _, s := range strs {
		if !letter.MatchString(s) {
			continue
		}
		for _, b := range BannedHits(s, banned) {
			found = append(found, Finding{"LC-2", s, "banned word '" + b + "'"})
		}
		if !allowed[s] {
			found = append(found, Finding{"LC-2", s, "not in the words table"})
		}
		for _, why := range PlainHits(s) {
			found = append(found, Finding{"LC-31", s, why})
		}
	}
	return found
}

var litRx = regexp.MustCompile("\"((?:[^\"\\\\\\n]|\\\\.)*)\"|`([^`]*)`")

// Literals returns the string literals of Go source: "..." and `...`.
func Literals(src string) []string {
	var out []string
	for _, m := range litRx.FindAllStringSubmatch(src, -1) {
		if m[2] != "" || m[1] == "" {
			out = append(out, m[2])
			continue
		}
		if u, err := strconv.Unquote(`"` + m[1] + `"`); err == nil {
			out = append(out, u)
		}
	}
	return out
}

func FindLifecycle(root string) (string, error) {
	dir := filepath.Join(root, "docs", "design-system")
	entries, err := os.ReadDir(dir)
	if err != nil {
		return "", err
	}
	var nums []int
	for _, e := range entries {
		if n := e.Name(); len(n) > 1 && n[0] == 'v' {
			if k, err := strconv.Atoi(n[1:]); err == nil && k > 0 {
				nums = append(nums, k)
			}
		}
	}
	sort.Sort(sort.Reverse(sort.IntSlice(nums)))
	names := []string{}
	for _, k := range nums {
		names = append(names, fmt.Sprintf("v%d", k))
	}
	for _, n := range append(names, "next-version") {
		f := filepath.Join(dir, n, "lifecycle.json")
		if _, err := os.Stat(f); err == nil {
			return f, nil
		}
	}
	return "", fmt.Errorf("no lifecycle.json under docs/design-system")
}

// ScanRoot checks every Go file (not _test.go) under Config.LifecycleFiles.
func ScanRoot(root string) ([]Finding, error) {
	lc, err := FindLifecycle(root)
	if err != nil {
		return nil, err
	}
	raw, err := os.ReadFile(lc)
	if err != nil {
		return nil, err
	}
	var doc struct {
		Words Words `json:"words"`
	}
	if err := json.Unmarshal(raw, &doc); err != nil {
		return nil, err
	}
	var found []Finding
	for _, f := range Config.LifecycleFiles {
		_ = filepath.Walk(filepath.Join(root, f), func(p string, info os.FileInfo, err error) error {
			if err != nil || info.IsDir() || !strings.HasSuffix(p, ".go") || strings.HasSuffix(p, "_test.go") {
				return nil
			}
			src, _ := os.ReadFile(p)
			found = append(found, CheckStrings(Literals(string(src)), doc.Words)...)
			return nil
		})
	}
	return found, nil
}
