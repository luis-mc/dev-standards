// Package guards holds the repository-wide guard tests (STACKSPEC 13.5).
//
// A guard test scans the source or the specs as a whole, so it is never scoped
// by package: the branch gate and the pre-push hook run every test named
// TestGuard* (`go test -run "^TestGuard" ./...`) whatever changed. Add a guard
// by adding a TestGuard* function anywhere in the module; this directory is just
// where the starter lives.
package guards

import (
	"bufio"
	"io/fs"
	"os"
	"path/filepath"
	"regexp"
	"strconv"
	"strings"
	"testing"
)

// Built from pieces so this file does not contain a marker line itself.
var (
	markerStart = regexp.MustCompile("^" + strings.Repeat("<", 7) + "( |$)")
	markerSep   = regexp.MustCompile("^" + strings.Repeat("=", 7) + "$")
	markerEnd   = regexp.MustCompile("^" + strings.Repeat(">", 7) + "( |$)")
)

// Markdown and plain text are excluded: seven "=" alone on a line is a setext
// heading underline there, not a conflict.
var scanned = map[string]bool{
	".go": true, ".mod": true, ".sum": true, ".json": true, ".yml": true,
	".yaml": true, ".toml": true, ".sql": true, ".sh": true, ".ts": true,
	".tsx": true, ".js": true, ".css": true, ".html": true,
}

var skipDirs = map[string]bool{
	".git": true, "node_modules": true, "vendor": true, ".delivery": true,
}

// moduleRoot walks up from the test's working directory to the directory that
// holds go.work, go.mod or .git.
func moduleRoot(t *testing.T) string {
	t.Helper()
	dir, err := os.Getwd()
	if err != nil {
		t.Fatal(err)
	}
	topModule := ""
	for {
		for _, marker := range []string{".git", "go.work"} {
			if _, err := os.Stat(filepath.Join(dir, marker)); err == nil {
				return dir
			}
		}
		if _, err := os.Stat(filepath.Join(dir, "go.mod")); err == nil {
			topModule = dir
		}
		parent := filepath.Dir(dir)
		if parent == dir {
			break
		}
		dir = parent
	}
	if topModule == "" {
		t.Fatal("no repository root (.git, go.work or go.mod) above the working directory")
	}
	return topModule
}

// otherCheckout reports whether dir holds its own .git: another checkout (an
// agent's worktree under .claude/worktrees, a submodule). Its files are in
// whatever state that work is in right now, mid-merge included; they are not
// this tree.
func otherCheckout(dir string) bool {
	_, err := os.Stat(filepath.Join(dir, ".git"))
	return err == nil
}

func TestGuardNoConflictMarkers(t *testing.T) {
	root := moduleRoot(t)
	files := 0
	var hits []string

	err := filepath.WalkDir(root, func(path string, d fs.DirEntry, err error) error {
		if err != nil {
			return err
		}
		if d.IsDir() {
			if skipDirs[d.Name()] {
				return filepath.SkipDir
			}
			if path != root && otherCheckout(path) {
				return filepath.SkipDir
			}
			return nil
		}
		if !scanned[strings.ToLower(filepath.Ext(path))] {
			return nil
		}
		f, err := os.Open(path)
		if err != nil {
			return err
		}
		defer f.Close()
		files++
		sc := bufio.NewScanner(f)
		sc.Buffer(make([]byte, 0, 64*1024), 8*1024*1024)
		for n := 1; sc.Scan(); n++ {
			line := strings.TrimRight(sc.Text(), "\r")
			if markerStart.MatchString(line) || markerSep.MatchString(line) || markerEnd.MatchString(line) {
				rel, _ := filepath.Rel(root, path)
				hits = append(hits, filepath.ToSlash(rel)+":"+strconv.Itoa(n)+": "+line)
			}
		}
		return sc.Err()
	})
	if err != nil {
		t.Fatal(err)
	}
	if files == 0 {
		t.Fatal("scanned no files; an empty scan would pass for the wrong reason")
	}
	if len(hits) > 0 {
		t.Fatalf("merge-conflict markers found:\n%s", strings.Join(hits, "\n"))
	}
}
