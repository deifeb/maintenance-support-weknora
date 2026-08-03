package maintenanceproxy

import (
	"bufio"
	"context"
	"encoding/json"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"net/url"
	"reflect"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"
)

const proxyTestSigningSecret = "01234567890123456789012345678901"

func newProxyTestSigner(t *testing.T) *Signer {
	t.Helper()
	signer, err := NewSigner(
		[]byte(proxyTestSigningSecret),
		"weknora",
		"maintenance-api",
		180*time.Second,
	)
	if err != nil {
		t.Fatalf("NewSigner() error = %v", err)
	}
	return signer
}

func fixedActorResolver(actor Actor, err error) ActorResolver {
	return func(*gin.Context) (Actor, error) {
		return actor, err
	}
}

func TestNewRejectsInvalidProxyConfiguration(t *testing.T) {
	signer := newProxyTestSigner(t)
	resolver := fixedActorResolver(Actor{}, nil)

	tests := []struct {
		name     string
		baseURL  string
		signer   *Signer
		resolver ActorResolver
		timeout  time.Duration
		want     string
	}{
		{name: "nil signer", baseURL: "http://127.0.0.1:8100", resolver: resolver, timeout: 30 * time.Second, want: "signer"},
		{name: "nil resolver", baseURL: "http://127.0.0.1:8100", signer: signer, timeout: 30 * time.Second, want: "resolver"},
		{name: "zero timeout", baseURL: "http://127.0.0.1:8100", signer: signer, resolver: resolver, timeout: 0, want: "timeout"},
		{name: "relative URL", baseURL: "maintenance-api:8100", signer: signer, resolver: resolver, timeout: 30 * time.Second, want: "absolute"},
		{name: "unsupported scheme", baseURL: "ftp://maintenance-api:8100", signer: signer, resolver: resolver, timeout: 30 * time.Second, want: "http"},
		{name: "path prefix", baseURL: "http://maintenance-api:8100/backend", signer: signer, resolver: resolver, timeout: 30 * time.Second, want: "service root"},
		{name: "userinfo", baseURL: "http://user:pass@maintenance-api:8100", signer: signer, resolver: resolver, timeout: 30 * time.Second, want: "userinfo"},
		{name: "query", baseURL: "http://maintenance-api:8100?debug=1", signer: signer, resolver: resolver, timeout: 30 * time.Second, want: "query"},
		{name: "fragment", baseURL: "http://maintenance-api:8100#debug", signer: signer, resolver: resolver, timeout: 30 * time.Second, want: "fragment"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := New(tt.baseURL, tt.signer, tt.resolver, tt.timeout)
			if err == nil || !strings.Contains(strings.ToLower(err.Error()), strings.ToLower(tt.want)) {
				t.Fatalf("New() error = %v, want containing %q", err, tt.want)
			}
		})
	}
}

func TestNewClonesTransportAndDisablesEnvironmentProxy(t *testing.T) {
	signer := newProxyTestSigner(t)
	proxy, err := New(
		"http://127.0.0.1:8100/",
		signer,
		fixedActorResolver(Actor{}, errors.New("not used")),
		17*time.Second,
	)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}

	transport, ok := proxy.reverse.Transport.(*http.Transport)
	if !ok {
		t.Fatalf("transport type = %T, want *http.Transport", proxy.reverse.Transport)
	}
	if transport == http.DefaultTransport {
		t.Fatal("proxy mutated http.DefaultTransport instead of cloning it")
	}
	if transport.ResponseHeaderTimeout != 17*time.Second {
		t.Fatalf("ResponseHeaderTimeout = %v, want 17s", transport.ResponseHeaderTimeout)
	}
	if transport.Proxy != nil {
		t.Fatal("transport.Proxy must be nil for direct internal service connections")
	}
}

func TestNormalizeProxyTarget(t *testing.T) {
	tests := []struct {
		name      string
		target    *url.URL
		wantPath  string
		wantQuery string
		wantErr   bool
	}{
		{
			name:      "root",
			target:    &url.URL{Path: "/api/maintenance/"},
			wantPath:  "/api/",
			wantQuery: "",
		},
		{
			name:      "resource with repeated query values",
			target:    &url.URL{Path: "/api/maintenance/v1/items", RawQuery: "tag=b&tag=a&q=x+y"},
			wantPath:  "/api/v1/items",
			wantQuery: "q=x+y&tag=b&tag=a",
		},
		{name: "missing trailing slash", target: &url.URL{Path: "/api/maintenance"}, wantErr: true},
		{name: "wrong prefix", target: &url.URL{Path: "/api/other/v1"}, wantErr: true},
		{name: "double slash", target: &url.URL{Path: "/api/maintenance/v1//items"}, wantErr: true},
		{name: "dot segment", target: &url.URL{Path: "/api/maintenance/v1/./items"}, wantErr: true},
		{name: "parent segment", target: &url.URL{Path: "/api/maintenance/v1/../admin"}, wantErr: true},
		{name: "backslash", target: &url.URL{Path: "/api/maintenance/v1\\admin"}, wantErr: true},
		{name: "NUL", target: &url.URL{Path: "/api/maintenance/v1/\x00admin"}, wantErr: true},
		{name: "encoded slash", target: &url.URL{Path: "/api/maintenance/v1/admin", RawPath: "/api/maintenance/v1%2fadmin"}, wantErr: true},
		{name: "encoded dot", target: &url.URL{Path: "/api/maintenance/v1/../admin", RawPath: "/api/maintenance/v1/%2e%2e/admin"}, wantErr: true},
		{name: "invalid raw path", target: &url.URL{Path: "/api/maintenance/v1/items", RawPath: "/api/maintenance/%zz"}, wantErr: true},
		{name: "invalid query escape", target: &url.URL{Path: "/api/maintenance/v1/items", RawQuery: "q=%zz"}, wantErr: true},
		{name: "ambiguous semicolon query", target: &url.URL{Path: "/api/maintenance/v1/items", RawQuery: "a=1;b=2"}, wantErr: true},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			gotPath, gotQuery, err := normalizeProxyTarget(tt.target)
			if tt.wantErr {
				if err == nil {
					t.Fatalf("normalizeProxyTarget() error = nil")
				}
				return
			}
			if err != nil {
				t.Fatalf("normalizeProxyTarget() error = %v", err)
			}
			if gotPath != tt.wantPath || gotQuery != tt.wantQuery {
				t.Fatalf("normalizeProxyTarget() = (%q, %q), want (%q, %q)", gotPath, gotQuery, tt.wantPath, tt.wantQuery)
			}
		})
	}
}

func TestNormalizeTrustedRequestID(t *testing.T) {
	tests := []struct {
		name    string
		value   string
		want    string
		wantErr bool
	}{
		{name: "trim", value: "  r-1  ", want: "r-1"},
		{name: "blank", value: "   ", wantErr: true},
		{name: "too long", value: strings.Repeat("a", 129), wantErr: true},
		{name: "newline", value: "r-1\nforged", wantErr: true},
		{name: "control", value: "r-1\x00forged", wantErr: true},
	}
	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got, err := normalizeTrustedRequestID(tt.value)
			if tt.wantErr {
				if err == nil {
					t.Fatal("normalizeTrustedRequestID() error = nil")
				}
				return
			}
			if err != nil || got != tt.want {
				t.Fatalf("normalizeTrustedRequestID() = %q, %v", got, err)
			}
		})
	}
}

func TestProxyRejectsUnsupportedMethodsAndUpgradesBeforeUpstream(t *testing.T) {
	proxy := newTestProxy(t, "http://127.0.0.1:8100", fixedActorResolver(Actor{}, errors.New("must not run")))

	tests := []struct {
		name       string
		method     string
		headers    http.Header
		wantStatus int
		wantCode   string
	}{
		{name: "CONNECT", method: http.MethodConnect, wantStatus: 405, wantCode: "MAINTENANCE_METHOD_NOT_ALLOWED"},
		{name: "TRACE", method: http.MethodTrace, wantStatus: 405, wantCode: "MAINTENANCE_METHOD_NOT_ALLOWED"},
		{name: "custom", method: "BREW", wantStatus: 405, wantCode: "MAINTENANCE_METHOD_NOT_ALLOWED"},
		{
			name:   "websocket upgrade",
			method: http.MethodGet,
			headers: http.Header{
				"Connection": {"keep-alive, Upgrade"},
				"Upgrade":    {"websocket"},
			},
			wantStatus: 400,
			wantCode:   "MAINTENANCE_PROTOCOL_UPGRADE_NOT_SUPPORTED",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			request := httptest.NewRequest(tt.method, "http://weknora.test/api/maintenance/v1/items", nil)
			request.Header = tt.headers.Clone()
			response := serveProxyRequest(proxy, request)
			assertProxyError(t, response, tt.wantStatus, tt.wantCode)
		})
	}
}

func TestProxyRejectsInvalidPathBeforeActorResolution(t *testing.T) {
	calls := 0
	proxy := newTestProxy(t, "http://127.0.0.1:8100", func(*gin.Context) (Actor, error) {
		calls++
		return Actor{}, nil
	})

	request := httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/items", nil)
	request.URL.Path = "/api/maintenance/v1/../admin"
	response := serveProxyRequest(proxy, request)

	assertProxyError(t, response, 400, "MAINTENANCE_INVALID_PROXY_PATH")
	if calls != 0 {
		t.Fatalf("actor resolver calls = %d, want 0", calls)
	}
}

func newTestProxy(t *testing.T, baseURL string, resolver ActorResolver) *Proxy {
	t.Helper()
	proxy, err := New(baseURL, newProxyTestSigner(t), resolver, 30*time.Second)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	return proxy
}

type proxyTestResponseWriter struct {
	*httptest.ResponseRecorder
}

func (writer *proxyTestResponseWriter) CloseNotify() <-chan bool {
	return make(chan bool)
}

func serveProxyRequest(proxy *Proxy, request *http.Request) *httptest.ResponseRecorder {
	response := httptest.NewRecorder()
	writer := &proxyTestResponseWriter{ResponseRecorder: response}
	context, _ := gin.CreateTestContext(writer)
	context.Request = request
	proxy.ServeHTTP(context)
	context.Writer.WriteHeaderNow()
	return response
}

func assertProxyError(t *testing.T, response *httptest.ResponseRecorder, status int, code string) {
	t.Helper()
	if response.Code != status {
		t.Fatalf("status = %d, want %d; body=%s", response.Code, status, response.Body.String())
	}
	var envelope proxyErrorEnvelope
	if err := json.Unmarshal(response.Body.Bytes(), &envelope); err != nil {
		t.Fatalf("decode proxy error: %v", err)
	}
	if envelope.Success || envelope.Error.Code != code || envelope.Error.Details.RequestID == "" {
		t.Fatalf("unexpected proxy error envelope: %+v", envelope)
	}
	if response.Header().Get("X-Request-ID") != envelope.Error.Details.RequestID {
		t.Fatalf("X-Request-ID does not match error details")
	}
	if response.Header().Get("Cache-Control") != "no-store" {
		t.Fatalf("Cache-Control = %q, want no-store", response.Header().Get("Cache-Control"))
	}
	if response.Header().Get("X-Content-Type-Options") != "nosniff" {
		t.Fatalf("X-Content-Type-Options = %q, want nosniff", response.Header().Get("X-Content-Type-Options"))
	}
}

type capturedUpstreamRequest struct {
	method   string
	path     string
	rawQuery string
	host     string
	header   http.Header
	body     string
}

func TestProxyRewritesRequestAndInjectsInternalIdentity(t *testing.T) {
	captured := make(chan capturedUpstreamRequest, 1)
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		body, err := io.ReadAll(request.Body)
		if err != nil {
			t.Errorf("read body: %v", err)
			writer.WriteHeader(http.StatusInternalServerError)
			return
		}
		captured <- capturedUpstreamRequest{
			method:   request.Method,
			path:     request.URL.Path,
			rawQuery: request.URL.RawQuery,
			host:     request.Host,
			header:   request.Header.Clone(),
			body:     string(body),
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(writer, `{"success":true}`)
	}))
	defer upstream.Close()

	proxy := newTestProxy(t, upstream.URL, fixedActorResolver(Actor{
		UserID:    "u-1",
		TenantID:  "t-1",
		Roles:     []string{"contributor"},
		RequestID: "r-1",
	}, nil))

	request := httptest.NewRequest(
		http.MethodPost,
		"http://weknora.test/api/maintenance/v1/items?tag=b&tag=a&q=x",
		strings.NewReader(`{"name":"pump"}`),
	)
	request.RemoteAddr = "192.0.2.10:4321"
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "idem-1")
	request.Header.Set("If-Match", `"v3"`)

	response := serveProxyRequest(proxy, request)
	if response.Code != http.StatusOK {
		t.Fatalf("status = %d; body=%s", response.Code, response.Body.String())
	}

	got := <-captured
	if got.method != http.MethodPost || got.path != "/api/v1/items" {
		t.Fatalf("upstream request = %s %s", got.method, got.path)
	}
	if got.rawQuery != "q=x&tag=b&tag=a" {
		t.Fatalf("query = %q", got.rawQuery)
	}
	if got.host != strings.TrimPrefix(upstream.URL, "http://") {
		t.Fatalf("Host = %q", got.host)
	}
	if got.header.Get("Idempotency-Key") != "idem-1" || got.header.Get("If-Match") != `"v3"` {
		t.Fatal("business headers were not preserved")
	}
	if got.header.Get("X-Request-ID") != "r-1" {
		t.Fatalf("X-Request-ID = %q", got.header.Get("X-Request-ID"))
	}
	if got.header.Get("X-Forwarded-Host") != "weknora.test" || got.header.Get("X-Forwarded-Proto") != "http" {
		t.Fatalf("forwarded headers = host:%q proto:%q", got.header.Get("X-Forwarded-Host"), got.header.Get("X-Forwarded-Proto"))
	}
	if got.body != `{"name":"pump"}` {
		t.Fatalf("body = %s", got.body)
	}

	authorization := got.header.Get("Authorization")
	if !strings.HasPrefix(authorization, "Bearer ") {
		t.Fatalf("Authorization = %q", authorization)
	}
	claims := parseProxyToken(t, strings.TrimPrefix(authorization, "Bearer "))
	if claims.Subject != "u-1" || claims.TenantID != "t-1" || claims.RequestID != "r-1" {
		t.Fatalf("unexpected claims: %+v", claims)
	}
	if !reflect.DeepEqual(claims.Roles, []string{"contributor"}) {
		t.Fatalf("roles = %v", claims.Roles)
	}
}

func TestProxyAllowsStandardMethods(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer upstream.Close()

	proxy := newTestProxy(t, upstream.URL, fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-method",
	}, nil))
	methods := []string{
		http.MethodGet,
		http.MethodHead,
		http.MethodPost,
		http.MethodPut,
		http.MethodPatch,
		http.MethodDelete,
		http.MethodOptions,
	}
	for _, method := range methods {
		t.Run(method, func(t *testing.T) {
			response := serveProxyRequest(proxy, httptest.NewRequest(method, "http://weknora.test/api/maintenance/v1/items", nil))
			if response.Code != http.StatusNoContent {
				t.Fatalf("status = %d; body=%s", response.Code, response.Body.String())
			}
		})
	}
}

func TestProxyStripsUntrustedRequestHeaders(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		forbidden := []string{
			"Cookie",
			"Proxy-Authorization",
			"X-Tenant-ID",
			"X-User-ID",
			"X-User-Roles",
			"X-Internal-Authorization",
			"X-Internal-Test",
			"X-Maintenance-Debug",
			"Forwarded",
			"X-Forwarded-Port",
			"X-Real-IP",
		}
		for _, name := range forbidden {
			if value := request.Header.Get(name); value != "" {
				t.Errorf("%s leaked upstream as %q", name, value)
			}
		}
		if request.Header.Get("Authorization") == "Bearer browser-token" {
			t.Error("browser bearer token leaked upstream")
		}
		if request.Header.Get("X-Forwarded-For") != "192.0.2.10" {
			t.Errorf("X-Forwarded-For = %q", request.Header.Get("X-Forwarded-For"))
		}
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer upstream.Close()

	proxy := newTestProxy(t, upstream.URL, fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-1",
	}, nil))
	request := httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/items", nil)
	request.RemoteAddr = "192.0.2.10:4321"
	request.Header.Set("Authorization", "Bearer browser-token")
	request.Header.Set("Cookie", "session=browser")
	request.Header.Set("Proxy-Authorization", "Basic browser")
	request.Header.Set("X-Tenant-ID", "spoofed")
	request.Header.Set("X-User-ID", "spoofed")
	request.Header.Set("X-User-Roles", "admin")
	request.Header.Set("X-Internal-Authorization", "spoofed")
	request.Header.Set("X-Internal-Test", "spoofed")
	request.Header.Set("X-Maintenance-Debug", "true")
	request.Header.Set("Forwarded", "for=attacker")
	request.Header.Set("X-Forwarded-For", "203.0.113.99")
	request.Header.Set("X-Forwarded-Host", "evil.test")
	request.Header.Set("X-Forwarded-Proto", "https")
	request.Header.Set("X-Forwarded-Port", "443")
	request.Header.Set("X-Real-IP", "203.0.113.99")

	response := serveProxyRequest(proxy, request)
	if response.Code != http.StatusNoContent {
		t.Fatalf("status = %d; body=%s", response.Code, response.Body.String())
	}
	if request.Header.Get("Authorization") != "Bearer browser-token" {
		t.Fatal("ServeHTTP mutated the original browser request")
	}
}

func parseProxyToken(t *testing.T, raw string) *Claims {
	t.Helper()
	parsed, err := jwt.ParseWithClaims(
		raw,
		&Claims{},
		func(token *jwt.Token) (any, error) {
			if token.Method != jwt.SigningMethodHS256 {
				t.Fatalf("signing method = %v, want HS256", token.Method)
			}
			return []byte(proxyTestSigningSecret), nil
		},
		jwt.WithValidMethods([]string{"HS256"}),
		jwt.WithAudience("maintenance-api"),
		jwt.WithIssuer("weknora"),
	)
	if err != nil {
		t.Fatalf("parse internal token: %v", err)
	}
	claims, ok := parsed.Claims.(*Claims)
	if !ok || !parsed.Valid {
		t.Fatalf("invalid claims type or token")
	}
	return claims
}

func TestProxyHardensResponseHeadersAndRewritesLocation(t *testing.T) {
	var upstreamURL string
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Set-Cookie", "upstream=session")
		writer.Header().Set("Server", "uvicorn")
		writer.Header().Set("Via", "internal-gateway")
		writer.Header().Set("X-Powered-By", "FastAPI")
		writer.Header().Set("Alt-Svc", `h3=":443"`)
		writer.Header().Set("Refresh", "0;url=http://internal")
		writer.Header().Set("X-Internal-Debug", "secret")
		writer.Header().Set("X-Maintenance-Node", "node-1")
		writer.Header().Set("X-Request-ID", "spoofed-upstream")
		writer.Header().Set("ETag", `"v3"`)
		writer.Header().Set("Content-Disposition", `attachment; filename="report.csv"`)
		writer.Header().Set("Retry-After", "5")
		writer.Header().Set("Location", upstreamURL+"/api/v1/reports/1?download=1#result")
		writer.WriteHeader(http.StatusCreated)
	}))
	upstreamURL = upstream.URL
	defer upstream.Close()

	proxy := newTestProxy(t, upstream.URL, fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-1",
	}, nil))
	response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodPost, "http://weknora.test/api/maintenance/v1/reports", nil))

	if response.Code != http.StatusCreated {
		t.Fatalf("status = %d; body=%s", response.Code, response.Body.String())
	}
	for _, name := range []string{"Set-Cookie", "Server", "Via", "X-Powered-By", "Alt-Svc", "Refresh", "X-Internal-Debug", "X-Maintenance-Node"} {
		if value := response.Header().Get(name); value != "" {
			t.Errorf("response header %s leaked as %q", name, value)
		}
	}
	if response.Header().Get("ETag") != `"v3"` || response.Header().Get("Retry-After") != "5" {
		t.Error("business response headers were removed")
	}
	if response.Header().Get("X-Request-ID") != "r-1" {
		t.Errorf("X-Request-ID = %q", response.Header().Get("X-Request-ID"))
	}
	if response.Header().Get("Location") != "/api/maintenance/v1/reports/1?download=1#result" {
		t.Errorf("Location = %q", response.Header().Get("Location"))
	}
}

func TestProxyRewritesRelativeLocation(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Location", "/api/v1/reports/2?download=1#result")
		writer.WriteHeader(http.StatusFound)
	}))
	defer upstream.Close()

	proxy := newTestProxy(t, upstream.URL, fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-relative",
	}, nil))
	response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/reports/2", nil))
	if response.Code != http.StatusFound {
		t.Fatalf("status = %d; body=%s", response.Code, response.Body.String())
	}
	if response.Header().Get("Location") != "/api/maintenance/v1/reports/2?download=1#result" {
		t.Fatalf("Location = %q", response.Header().Get("Location"))
	}
}

func TestProxyRejectsExternalLocation(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Location", "https://evil.example/api/v1/reports/1")
		writer.WriteHeader(http.StatusFound)
	}))
	defer upstream.Close()

	proxy := newTestProxy(t, upstream.URL, fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-1",
	}, nil))
	response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/reports/1", nil))
	assertProxyError(t, response, 502, "MAINTENANCE_INVALID_UPSTREAM_RESPONSE")
	if strings.Contains(response.Body.String(), "evil.example") || strings.Contains(response.Body.String(), upstream.URL) {
		t.Fatal("proxy error leaked an upstream address")
	}
}

func TestProxyMapsActorAndSigningFailures(t *testing.T) {
	t.Run("actor resolver", func(t *testing.T) {
		proxy := newTestProxy(t, "http://127.0.0.1:8100", fixedActorResolver(Actor{RequestID: "r-actor"}, errors.New("session missing")))
		response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/items", nil))
		assertProxyError(t, response, 401, "MAINTENANCE_ACTOR_UNAVAILABLE")
		if response.Header().Get("X-Request-ID") != "r-actor" {
			t.Fatalf("request ID = %q", response.Header().Get("X-Request-ID"))
		}
		if strings.Contains(response.Body.String(), "session missing") {
			t.Fatal("resolver error leaked to the browser")
		}
	})

	t.Run("invalid trusted request ID", func(t *testing.T) {
		proxy := newTestProxy(t, "http://127.0.0.1:8100", fixedActorResolver(Actor{
			UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-1\nforged",
		}, nil))
		response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/items", nil))
		assertProxyError(t, response, 500, "MAINTENANCE_IDENTITY_EXCHANGE_FAILED")
		if strings.Contains(response.Header().Get("X-Request-ID"), "forged") {
			t.Fatal("invalid request ID reached the response")
		}
	})

	t.Run("signing", func(t *testing.T) {
		proxy := newTestProxy(t, "http://127.0.0.1:8100", fixedActorResolver(Actor{
			UserID: "u-1", TenantID: "t-1", Roles: []string{"owner"}, RequestID: "r-sign",
		}, nil))
		response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/items", nil))
		assertProxyError(t, response, 500, "MAINTENANCE_IDENTITY_EXCHANGE_FAILED")
		if strings.Contains(response.Body.String(), "owner") {
			t.Fatal("signer error leaked to the browser")
		}
	})
}

type roundTripperFunc func(*http.Request) (*http.Response, error)

func (function roundTripperFunc) RoundTrip(request *http.Request) (*http.Response, error) {
	return function(request)
}

func TestProxyMapsTransportFailureWithoutLeakingDetails(t *testing.T) {
	proxy := newTestProxy(t, "http://127.0.0.1:8100", fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-upstream",
	}, nil))
	proxy.reverse.Transport = roundTripperFunc(func(*http.Request) (*http.Response, error) {
		return nil, errors.New("dial tcp maintenance-api:8100: connection refused")
	})

	response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/items", nil))
	assertProxyError(t, response, 502, "MAINTENANCE_UPSTREAM_UNAVAILABLE")
	if strings.Contains(response.Body.String(), "maintenance-api") || strings.Contains(response.Body.String(), "connection refused") {
		t.Fatal("transport details leaked to the browser")
	}
}

func TestProxyMapsResponseHeaderTimeout(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		time.Sleep(200 * time.Millisecond)
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer upstream.Close()

	proxy, err := New(upstream.URL, newProxyTestSigner(t), fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-timeout",
	}, nil), 25*time.Millisecond)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}

	response := serveProxyRequest(proxy, httptest.NewRequest(http.MethodGet, "http://weknora.test/api/maintenance/v1/items", nil))
	assertProxyError(t, response, 502, "MAINTENANCE_UPSTREAM_UNAVAILABLE")
}

func newProxyHTTPServer(t *testing.T, proxy *Proxy) *httptest.Server {
	t.Helper()
	return httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		context, _ := gin.CreateTestContext(writer)
		context.Request = request
		proxy.ServeHTTP(context)
	}))
}

func readSSEEvent(t *testing.T, reader *bufio.Reader) string {
	t.Helper()
	var builder strings.Builder
	for {
		line, err := reader.ReadString('\n')
		if err != nil {
			t.Fatalf("read SSE event: %v", err)
		}
		builder.WriteString(line)
		if line == "\n" {
			return builder.String()
		}
	}
}

func TestProxyStreamsSSEBeyondHeaderTimeoutAndCancelsUpstream(t *testing.T) {
	firstFlushed := make(chan struct{})
	releaseSecond := make(chan struct{})
	upstreamCanceled := make(chan struct{})
	lastEventID := make(chan string, 1)

	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		lastEventID <- request.Header.Get("Last-Event-ID")
		writer.Header().Set("Content-Type", "text/event-stream")
		writer.Header().Set("Cache-Control", "no-cache")
		flusher, ok := writer.(http.Flusher)
		if !ok {
			t.Error("upstream writer does not implement http.Flusher")
			return
		}

		_, _ = io.WriteString(writer, "id: 1\nevent: progress\ndata: {\"percent\":10}\n\n")
		flusher.Flush()
		close(firstFlushed)

		select {
		case <-releaseSecond:
			_, _ = io.WriteString(writer, "id: 2\nevent: progress\ndata: {\"percent\":20}\n\n")
			flusher.Flush()
		case <-request.Context().Done():
			close(upstreamCanceled)
			return
		}

		<-request.Context().Done()
		close(upstreamCanceled)
	}))
	defer upstream.Close()

	proxy, err := New(upstream.URL, newProxyTestSigner(t), fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-sse",
	}, nil), 40*time.Millisecond)
	if err != nil {
		t.Fatalf("New() error = %v", err)
	}
	proxyServer := newProxyHTTPServer(t, proxy)
	defer proxyServer.Close()

	requestContext, cancel := context.WithCancel(context.Background())
	request, err := http.NewRequestWithContext(
		requestContext,
		http.MethodGet,
		proxyServer.URL+"/api/maintenance/v1/jobs/1/events",
		nil,
	)
	if err != nil {
		t.Fatalf("NewRequestWithContext() error = %v", err)
	}
	request.Header.Set("Accept", "text/event-stream")
	request.Header.Set("Last-Event-ID", "previous-7")

	response, err := http.DefaultClient.Do(request)
	if err != nil {
		t.Fatalf("proxy SSE request: %v", err)
	}
	defer response.Body.Close()
	if response.StatusCode != http.StatusOK {
		body, _ := io.ReadAll(response.Body)
		t.Fatalf("status = %d; body=%s", response.StatusCode, body)
	}
	if response.Header.Get("Content-Type") != "text/event-stream" {
		t.Fatalf("Content-Type = %q", response.Header.Get("Content-Type"))
	}

	select {
	case <-firstFlushed:
	case <-time.After(time.Second):
		t.Fatal("upstream did not flush the first event")
	}

	reader := bufio.NewReader(response.Body)
	firstEvent := readSSEEvent(t, reader)
	if !strings.Contains(firstEvent, `"percent":10`) {
		t.Fatalf("first event = %q", firstEvent)
	}

	time.Sleep(100 * time.Millisecond)
	close(releaseSecond)
	secondEvent := readSSEEvent(t, reader)
	if !strings.Contains(secondEvent, `"percent":20`) {
		t.Fatalf("second event = %q", secondEvent)
	}

	select {
	case value := <-lastEventID:
		if value != "previous-7" {
			t.Fatalf("Last-Event-ID = %q", value)
		}
	case <-time.After(time.Second):
		t.Fatal("upstream did not receive Last-Event-ID")
	}

	cancel()
	select {
	case <-upstreamCanceled:
	case <-time.After(time.Second):
		t.Fatal("client cancellation was not propagated upstream")
	}
}

func TestProxyDoesNotAppendJSONAfterSSEStreamEnds(t *testing.T) {
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		writer.Header().Set("Content-Type", "text/event-stream")
		flusher := writer.(http.Flusher)
		_, _ = io.WriteString(writer, "id: 1\nevent: done\ndata: {}\n\n")
		flusher.Flush()
	}))
	defer upstream.Close()

	proxy := newTestProxy(t, upstream.URL, fixedActorResolver(Actor{
		UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-eof",
	}, nil))
	proxyServer := newProxyHTTPServer(t, proxy)
	defer proxyServer.Close()

	response, err := http.Get(proxyServer.URL + "/api/maintenance/v1/jobs/1/events")
	if err != nil {
		t.Fatalf("proxy SSE request: %v", err)
	}
	defer response.Body.Close()
	body, err := io.ReadAll(response.Body)
	if err != nil {
		t.Fatalf("read SSE response: %v", err)
	}
	if !strings.Contains(string(body), "event: done") {
		t.Fatalf("SSE body = %q", body)
	}
	if strings.Contains(string(body), "MAINTENANCE_UPSTREAM_UNAVAILABLE") || strings.Contains(string(body), `"success":false`) {
		t.Fatal("proxy appended a JSON error after the SSE response started")
	}
}

func TestNewRejectsReplacedDefaultTransportWithoutPanicking(t *testing.T) {
	original := http.DefaultTransport
	http.DefaultTransport = roundTripperFunc(func(*http.Request) (*http.Response, error) {
		return nil, errors.New("not used")
	})
	defer func() { http.DefaultTransport = original }()

	_, err := New(
		"http://127.0.0.1:8100",
		newProxyTestSigner(t),
		fixedActorResolver(Actor{}, errors.New("not used")),
		30*time.Second,
	)
	if err == nil || !strings.Contains(err.Error(), "default transport") {
		t.Fatalf("New() error = %v, want default transport error", err)
	}
}

func TestReverseProxyFailsClosedWhenTrustedStateIsMissing(t *testing.T) {
	proxy := newTestProxy(t, "http://127.0.0.1:8100", fixedActorResolver(Actor{}, errors.New("not used")))
	outbound := make(chan *http.Request, 1)
	proxy.reverse.Transport = roundTripperFunc(func(request *http.Request) (*http.Response, error) {
		outbound <- request.Clone(request.Context())
		return nil, errors.New("blocked by test transport")
	})

	response := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "http://attacker.example/api/maintenance/v1/items", nil)
	request.Header.Set("Authorization", "Bearer browser-token")
	request.Header.Set("Cookie", "session=browser")
	proxy.reverse.ServeHTTP(response, request)

	assertProxyError(t, response, http.StatusBadGateway, "MAINTENANCE_UPSTREAM_UNAVAILABLE")
	got := <-outbound
	if got.URL.Scheme != "" || got.URL.Host != "" || got.Host != "" {
		t.Fatalf("missing-state request retained a routable target: URL=%s Host=%q", got.URL.String(), got.Host)
	}
	if got.Header.Get("Authorization") != "" || got.Header.Get("Cookie") != "" {
		t.Fatal("missing-state request retained untrusted credentials")
	}
}
