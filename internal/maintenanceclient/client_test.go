package maintenanceclient

import (
	"context"
	"encoding/json"
	"errors"
	"net/http"
	"net/http/httptest"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/Tencent/WeKnora/internal/config"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/golang-jwt/jwt/v5"
	"github.com/stretchr/testify/require"
)

const clientTestSecret = "01234567890123456789012345678901"

func testSigner(t *testing.T) *maintenanceproxy.Signer {
	t.Helper()

	signer, err := maintenanceproxy.NewSigner(
		[]byte(clientTestSecret),
		"weknora",
		"maintenance-api",
		180*time.Second,
	)
	require.NoError(t, err)
	return signer
}

func testConfig(baseURL string, timeout time.Duration) *config.MaintenanceConfig {
	return &config.MaintenanceConfig{
		Enabled:        true,
		BaseURL:        baseURL,
		SigningSecret:  clientTestSecret,
		Issuer:         "weknora",
		Audience:       "maintenance-api",
		TokenTTL:       180 * time.Second,
		RequestTimeout: timeout,
	}
}

func exactSource() types.MaintenanceProjectionProvenance {
	return types.MaintenanceProjectionProvenance{
		SchemaVersion:    "1.0",
		SourceKind:       "AI_MESSAGE_TRIGGER",
		AISessionID:      123,
		TriggerMessageID: 456,
	}
}

func exactActor() maintenanceproxy.Actor {
	return maintenanceproxy.Actor{
		UserID:    "user-7",
		TenantID:  "42",
		Roles:     []string{"viewer"},
		RequestID: "req-exact-turn",
	}
}

func validProjectionEnvelope() map[string]any {
	return map[string]any{
		"data": map[string]any{
			"schema_version": "1.0",
			"source": map[string]any{
				"kind":       "AI_MESSAGE_TRIGGER",
				"session_id": 123,
				"message_id": 456,
			},
			"cards": []any{
				map[string]any{
					"schema_version": "1.0",
					"type":           "CALCULATION",
					"title":          "Calculation created",
					"summary":        "Open the calculation progress page.",
					"status":         "PENDING",
					"target": map[string]any{
						"object_type":      "CALCULATION_GROUP",
						"object_id":        35,
						"observed_version": 1,
						"navigation_path":  "/platform/maintenance/calculations/35/progress",
					},
					"observed_at": "2026-08-29T00:00:00Z",
					"payload": map[string]any{
						"group_id":                35,
						"scenario_version_id":     7,
						"status":                  "PENDING",
						"primary_candidate_key":   "base",
						"current_candidate_count": 2,
						"observed_version":        1,
					},
				},
			},
		},
		"message": "",
		"meta": map[string]any{
			"request_id": "req-exact-turn",
			"tenant_id":  42,
		},
	}
}

func writeJSON(t *testing.T, w http.ResponseWriter, value any) {
	t.Helper()

	w.Header().Set("Content-Type", "application/json")
	require.NoError(t, json.NewEncoder(w).Encode(value))
}

func parseClientToken(t *testing.T, raw string) *maintenanceproxy.Claims {
	t.Helper()

	token, err := jwt.ParseWithClaims(
		raw,
		&maintenanceproxy.Claims{},
		func(token *jwt.Token) (any, error) {
			require.Equal(t, jwt.SigningMethodHS256, token.Method)
			return []byte(clientTestSecret), nil
		},
		jwt.WithIssuer("weknora"),
		jwt.WithAudience("maintenance-api"),
	)
	require.NoError(t, err)
	require.True(t, token.Valid)

	claims, ok := token.Claims.(*maintenanceproxy.Claims)
	require.True(t, ok)
	return claims
}

func TestRecoverExactTurnUsesExactPathAndSignedActor(t *testing.T) {
	var requests atomic.Int32

	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			requests.Add(1)

			require.Equal(t, http.MethodGet, r.Method)
			require.Equal(
				t,
				"/api/v1/ai/sessions/123/messages/456/business-cards",
				r.URL.Path,
			)
			require.Empty(t, r.URL.RawQuery)
			require.NotContains(t, r.URL.Path, "latest")

			require.Equal(
				t,
				"req-exact-turn",
				r.Header.Get("X-Request-ID"),
			)

			authorization := r.Header.Get("Authorization")
			require.True(
				t,
				strings.HasPrefix(authorization, "Bearer "),
			)
			claims := parseClientToken(
				t,
				strings.TrimPrefix(authorization, "Bearer "),
			)
			require.Equal(t, "user-7", claims.Subject)
			require.Equal(t, "42", claims.TenantID)
			require.Equal(t, []string{"viewer"}, claims.Roles)
			require.Equal(t, "req-exact-turn", claims.RequestID)

			writeJSON(t, w, validProjectionEnvelope())
		},
	))
	defer server.Close()

	client, err := New(
		testConfig(server.URL, 500*time.Millisecond),
		testSigner(t),
	)
	require.NoError(t, err)

	cards, err := client.RecoverExactTurn(
		context.Background(),
		exactActor(),
		exactSource(),
	)
	require.NoError(t, err)
	require.Len(t, cards, 1)
	require.Equal(t, "CALCULATION", cards[0].Type)
	require.EqualValues(t, 35, cards[0].Target.ObjectID)
	require.EqualValues(t, 1, cards[0].Target.ObservedVersion)
	require.EqualValues(t, 1, requests.Load())
}

func TestRecoverExactTurnDoesNotFallbackToLatestOnNotFound(t *testing.T) {
	var requests atomic.Int32
	var paths []string

	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			requests.Add(1)
			paths = append(paths, r.URL.Path)
			http.NotFound(w, r)
		},
	))
	defer server.Close()

	client, err := New(
		testConfig(server.URL, 500*time.Millisecond),
		testSigner(t),
	)
	require.NoError(t, err)

	_, err = client.RecoverExactTurn(
		context.Background(),
		exactActor(),
		exactSource(),
	)
	require.Error(t, err)
	require.EqualValues(t, 1, requests.Load())
	require.Equal(
		t,
		[]string{
			"/api/v1/ai/sessions/123/messages/456/business-cards",
		},
		paths,
	)
}

func TestRecoverExactTurnRejectsMismatchedSourceIdentity(t *testing.T) {
	envelope := validProjectionEnvelope()
	data := envelope["data"].(map[string]any)
	source := data["source"].(map[string]any)
	source["message_id"] = 999

	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			writeJSON(t, w, envelope)
		},
	))
	defer server.Close()

	client, err := New(
		testConfig(server.URL, 500*time.Millisecond),
		testSigner(t),
	)
	require.NoError(t, err)

	_, err = client.RecoverExactTurn(
		context.Background(),
		exactActor(),
		exactSource(),
	)
	require.Error(t, err)
}

func TestRecoverExactTurnRunsCoreSecondaryValidation(t *testing.T) {
	envelope := validProjectionEnvelope()
	data := envelope["data"].(map[string]any)
	cards := data["cards"].([]any)
	card := cards[0].(map[string]any)
	target := card["target"].(map[string]any)
	target["navigation_path"] = "https://evil.example/calculations/35"

	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			writeJSON(t, w, envelope)
		},
	))
	defer server.Close()

	client, err := New(
		testConfig(server.URL, 500*time.Millisecond),
		testSigner(t),
	)
	require.NoError(t, err)

	cardsResult, err := client.RecoverExactTurn(
		context.Background(),
		exactActor(),
		exactSource(),
	)
	require.Error(t, err)
	require.Nil(t, cardsResult)
}

func TestRecoverExactTurnUsesBoundedRequestTimeout(t *testing.T) {
	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			<-r.Context().Done()
		},
	))
	defer server.Close()

	client, err := New(
		testConfig(server.URL, 40*time.Millisecond),
		testSigner(t),
	)
	require.NoError(t, err)

	started := time.Now()
	_, err = client.RecoverExactTurn(
		context.Background(),
		exactActor(),
		exactSource(),
	)
	elapsed := time.Since(started)

	require.Error(t, err)
	require.True(
		t,
		errors.Is(err, context.DeadlineExceeded) ||
			strings.Contains(strings.ToLower(err.Error()), "deadline") ||
			strings.Contains(strings.ToLower(err.Error()), "timeout"),
	)
	require.Less(t, elapsed, time.Second)
}

func TestRecoverExactTurnRejectsIncompleteProvenanceWithoutNetworkCall(t *testing.T) {
	var requests atomic.Int32

	server := httptest.NewServer(http.HandlerFunc(
		func(w http.ResponseWriter, r *http.Request) {
			requests.Add(1)
			t.Fatal("network call must not occur for incomplete provenance")
		},
	))
	defer server.Close()

	client, err := New(
		testConfig(server.URL, 500*time.Millisecond),
		testSigner(t),
	)
	require.NoError(t, err)

	invalid := exactSource()
	invalid.TriggerMessageID = 0

	_, err = client.RecoverExactTurn(
		context.Background(),
		exactActor(),
		invalid,
	)
	require.Error(t, err)
	require.EqualValues(t, 0, requests.Load())
}
