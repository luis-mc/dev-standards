package updatercore

import (
	"net/http/httptest"
	"os"
	"os/exec"
	"testing"
)

// TestConformance runs the shared runner against this core. LIFECYCLE_CONFORMANCE is its path.
func TestConformance(t *testing.T) {
	runner := os.Getenv("LIFECYCLE_CONFORMANCE")
	if runner == "" {
		t.Skip("LIFECYCLE_CONFORMANCE is not set")
	}
	py := os.Getenv("PYTHON")
	if py == "" {
		py = "python3"
	}
	srv := httptest.NewServer(Handler(&Updater{}))
	defer srv.Close()
	out, err := exec.Command(py, runner, "--url", srv.URL).CombinedOutput()
	t.Log("\n" + string(out))
	if err != nil {
		t.Fatalf("runner failed: %v", err)
	}
}
