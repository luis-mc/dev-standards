package wordslint

import (
	"path/filepath"
	"strings"
	"testing"
)

// LC-2 and LC-31 (DS235a). The self-tests prove the rules; the last test scans the project.
var words = Words{States: map[string]map[string]string{"available": {"title": "Version {version} is ready."}}}

func TestCleanStringPasses(t *testing.T) {
	if f := CheckStrings([]string{"Version {version} is ready."}, words); len(f) != 0 {
		t.Fatalf("unexpected findings: %v", f)
	}
}

func TestEachBannedWordIsFlagged(t *testing.T) {
	for _, w := range DefaultBanned {
		if len(BannedHits("Press "+w+" to go", DefaultBanned)) == 0 {
			t.Errorf("not flagged: %s", w)
		}
	}
	if len(BannedHits("Nothing changed. Notes.", DefaultBanned)) != 0 {
		t.Errorf("a word that contains a banned one was flagged")
	}
}

func TestPlainNotices(t *testing.T) {
	cases := map[string]string{
		"Failed with 0x80070005":   "error code",
		"Error 1603":               "error code",
		"The server said HTTP 503": "HTTP status",
		"Done..":                   "doubled punctuation",
	}
	for text, want := range cases {
		if got := strings.Join(PlainHits(text), ","); !strings.Contains(got, want) {
			t.Errorf("%q: got %q, want %q", text, got, want)
		}
	}
	if len(PlainHits("Nothing changed.")) != 0 {
		t.Errorf("a plain notice was flagged")
	}
}

func TestStringNotInTableIsFlagged(t *testing.T) {
	if f := CheckStrings([]string{"Click here"}, words); len(f) != 1 || f[0].Why != "not in the words table" {
		t.Fatalf("got %v", f)
	}
}

func TestLiterals(t *testing.T) {
	got := Literals("a := \"x y\"\nb := `z w`")
	if len(got) != 2 || got[0] != "x y" || got[1] != "z w" {
		t.Fatalf("got %v", got)
	}
}

func TestProjectHasNoFinding(t *testing.T) {
	f, err := ScanRoot(filepath.Join("..", ".."))
	if err != nil {
		t.Fatal(err)
	}
	if len(f) != 0 {
		t.Fatalf("findings: %v", f)
	}
}
