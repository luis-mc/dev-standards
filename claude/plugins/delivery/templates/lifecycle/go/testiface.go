package updatercore

import (
	"crypto/ed25519"
	"encoding/hex"
	"encoding/json"
	"net/http"
	"strings"
	"sync"
)

// Handler is the test interface of ../CONTRACT.md over HTTP. Build it into test builds only.
func Handler(u *Updater) http.Handler {
	var mu sync.Mutex
	return http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		verb := strings.TrimPrefix(r.URL.Path, "/test/")
		var b struct {
			Version   string  `json:"version"`
			Paired    bool    `json:"paired"`
			Policy    string  `json:"policy"`
			Window    *Window `json:"window"`
			Channel   string  `json:"channel"`
			Idle      bool    `json:"idle"`
			Now       float64 `json:"now"`
			ServerURL string  `json:"server_url"`
			PublicKey string  `json:"public_key"`
			Seed      int64   `json:"seed"`
			Seconds   float64 `json:"seconds"`
			Pass      bool    `json:"pass"`
			Actor     string  `json:"actor"`
			Remote    bool    `json:"remote"`
			Click     bool    `json:"click"`
		}
		_ = json.NewDecoder(r.Body).Decode(&b)
		mu.Lock()
		defer mu.Unlock()
		if verb != "reset" && u.rng == nil {
			u.Reset("0.0.0", false, "automatic_when_idle", nil, "stable", true, 0, "", nil, 1)
		}
		out := func(v interface{}) {
			w.Header().Set("Content-Type", "application/json")
			_ = json.NewEncoder(w).Encode(v)
		}
		switch verb {
		case "reset":
			pub, err := hex.DecodeString(b.PublicKey)
			if err != nil || len(pub) != ed25519.PublicKeySize {
				out(map[string]string{"error": ErrBadKey.Error()})
				return
			}
			u.Reset(b.Version, b.Paired, b.Policy, b.Window, b.Channel, b.Idle, b.Now, b.ServerURL, pub, b.Seed)
		case "server.set":
			pub, _ := hex.DecodeString(b.PublicKey)
			u.server, u.pub = b.ServerURL, pub
		case "clock.set":
			u.Now = b.Now
		case "clock.advance":
			u.Advance(b.Seconds)
		case "idle.set":
			u.Idle = b.Idle
			u.Reeval()
		case "policy.set":
			u.Policy, u.Window = b.Policy, b.Window
			u.Reeval()
		case "selftest.set":
			u.SelfTestPass = b.Pass
		case "pair":
			u.SetPaired(b.Paired)
		case "install":
			u.Install(b.Actor, b.Remote, b.Click)
		case "check":
			ran := u.Check()
			out(map[string]interface{}{"ran": ran, "state": u.view()})
			return
		case "audit":
			out(map[string]interface{}{"rows": u.Rows})
			return
		case "settings":
			out(map[string]interface{}{"policy": u.Policy, "window": u.Window, "channel": u.Channel,
				"last_check": u.LastCheck, "last_result": u.LastResult})
			return
		case "state":
		default:
			out(map[string]string{"error": "unknown verb " + verb})
			return
		}
		out(u.view())
	})
}

func (u *Updater) view() map[string]interface{} {
	return map[string]interface{}{"state": u.State, "version": u.Version, "paired": u.Paired, "policy": u.Policy,
		"window": u.Window, "channel": u.Channel, "idle": u.Idle, "now": u.Now, "next_check_at": u.NextCheckAt,
		"retry_at": u.RetryAt, "history": u.History}
}
