package router

import (
	"context"
	"errors"
	"io"
	"net/http"
	"net/http/httptest"
	"reflect"
	"strings"
	"sync/atomic"
	"testing"
	"time"

	"github.com/gin-contrib/cors"
	"github.com/gin-gonic/gin"
	"github.com/golang-jwt/jwt/v5"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/middleware"
	"github.com/Tencent/WeKnora/internal/types"
)

type maintenanceSecurityResponseWriter struct {
	*httptest.ResponseRecorder
}

func (writer *maintenanceSecurityResponseWriter) CloseNotify() <-chan bool {
	return make(chan bool)
}

type maintenanceUpstreamRequest struct {
	URI           string
	Authorization string
	RequestID     string
	TenantID      string
	UserID        string
	UserRoles     string
	Cookie        string
	Internal      string
}

func newSecurityTestSigner(t *testing.T, secret []byte) *maintenanceproxy.Signer {
	t.Helper()

	signer, err := maintenanceproxy.NewSigner(secret, "weknora", "maintenance-api", 180*time.Second)
	if err != nil {
		t.Fatalf("maintenanceproxy.NewSigner() error = %v", err)
	}
	return signer
}

func newSecurityTestProxy(
	t *testing.T,
	upstreamURL string,
	signer *maintenanceproxy.Signer,
	resolver maintenanceproxy.ActorResolver,
) *maintenanceproxy.Proxy {
	t.Helper()

	proxy, err := maintenanceproxy.New(upstreamURL, signer, resolver, 5*time.Second)
	if err != nil {
		t.Fatalf("maintenanceproxy.New() error = %v", err)
	}
	return proxy
}

func withMaintenanceIdentity(values map[types.ContextKey]any) gin.HandlerFunc {
	return func(c *gin.Context) {
		ctx := c.Request.Context()
		for key, value := range values {
			ctx = context.WithValue(ctx, key, value)
		}
		c.Request = c.Request.WithContext(ctx)
		c.Next()
	}
}

func TestMaintenanceProxyExchangesTrustedWebIdentity(t *testing.T) {
	secret := []byte(strings.Repeat("m", 32))
	received := make(chan maintenanceUpstreamRequest, 1)
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		received <- maintenanceUpstreamRequest{
			URI:           request.URL.RequestURI(),
			Authorization: request.Header.Get("Authorization"),
			RequestID:     request.Header.Get("X-Request-ID"),
			TenantID:      request.Header.Get("X-Tenant-ID"),
			UserID:        request.Header.Get("X-User-ID"),
			UserRoles:     request.Header.Get("X-User-Roles"),
			Cookie:        request.Header.Get("Cookie"),
			Internal:      request.Header.Get("X-Maintenance-Internal"),
		}
		writer.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(writer, `{"ok":true}`)
	}))
	defer upstream.Close()

	signer := newSecurityTestSigner(t, secret)
	proxy := newSecurityTestProxy(t, upstream.URL, signer, maintenanceproxy.ResolveWebActor)
	engine := gin.New()
	engine.Use(withMaintenanceIdentity(map[types.ContextKey]any{
		types.RequestIDContextKey:   "req-security-1",
		types.PrincipalContextKey:   types.Principal{Type: types.PrincipalWebUser, ID: "user-42"},
		types.UserIDContextKey:      "user-42",
		types.TenantIDContextKey:    uint64(77),
		types.TenantRoleContextKey:  types.TenantRoleContributor,
		types.SystemAdminContextKey: false,
	}))
	RegisterMaintenanceRoutes(engine, proxy)
	handler := NewApplicationHandler(engine, proxy)

	recorder := httptest.NewRecorder()
	writer := &maintenanceSecurityResponseWriter{ResponseRecorder: recorder}
	request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs?status=open", nil)
	request.Header.Set("Authorization", "Bearer browser-controlled")
	request.Header.Set("Cookie", "session=browser-controlled")
	request.Header.Set("X-Tenant-ID", "999")
	request.Header.Set("X-User-ID", "attacker")
	request.Header.Set("X-User-Roles", "admin")
	request.Header.Set("X-Maintenance-Internal", "browser-controlled")

	handler.ServeHTTP(writer, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
	}

	var captured maintenanceUpstreamRequest
	select {
	case captured = <-received:
	case <-time.After(time.Second):
		t.Fatal("upstream request was not received")
	}

	if captured.URI != "/api/jobs?status=open" {
		t.Fatalf("upstream URI = %q", captured.URI)
	}
	if captured.RequestID != "req-security-1" {
		t.Fatalf("X-Request-ID = %q", captured.RequestID)
	}
	if captured.TenantID != "" || captured.UserID != "" || captured.UserRoles != "" || captured.Cookie != "" || captured.Internal != "" {
		t.Fatalf("browser identity headers leaked upstream: %#v", captured)
	}

	const bearerPrefix = "Bearer "
	if !strings.HasPrefix(captured.Authorization, bearerPrefix) {
		t.Fatalf("Authorization = %q", captured.Authorization)
	}
	claims := &maintenanceproxy.Claims{}
	token, err := jwt.ParseWithClaims(
		strings.TrimPrefix(captured.Authorization, bearerPrefix),
		claims,
		func(token *jwt.Token) (any, error) {
			if token.Method != jwt.SigningMethodHS256 {
				return nil, errors.New("unexpected signing method")
			}
			return secret, nil
		},
		jwt.WithIssuer("weknora"),
		jwt.WithAudience("maintenance-api"),
	)
	if err != nil || !token.Valid {
		t.Fatalf("parse internal token: token=%v err=%v", token, err)
	}
	if claims.Subject != "user-42" || claims.TenantID != "77" || claims.RequestID != "req-security-1" {
		t.Fatalf("claims = %#v", claims)
	}
	if !reflect.DeepEqual(claims.Roles, []string{"contributor"}) {
		t.Fatalf("roles = %#v", claims.Roles)
	}
	if claims.IssuedAt == nil || claims.ExpiresAt == nil {
		t.Fatal("token timestamps are missing")
	}
	if lifetime := claims.ExpiresAt.Time.Sub(claims.IssuedAt.Time); lifetime != 180*time.Second {
		t.Fatalf("token lifetime = %s", lifetime)
	}
}

func TestMaintenanceProxyRejectsMachinePrincipalBeforeUpstream(t *testing.T) {
	var upstreamCalls atomic.Int32
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		upstreamCalls.Add(1)
		writer.WriteHeader(http.StatusNoContent)
	}))
	defer upstream.Close()

	secret := []byte(strings.Repeat("m", 32))
	proxy := newSecurityTestProxy(t, upstream.URL, newSecurityTestSigner(t, secret), maintenanceproxy.ResolveWebActor)
	engine := gin.New()
	engine.Use(withMaintenanceIdentity(map[types.ContextKey]any{
		types.RequestIDContextKey:   "req-machine-1",
		types.PrincipalContextKey:   types.Principal{Type: types.PrincipalAPITenant, ID: "12:key-1"},
		types.UserIDContextKey:      "system-12",
		types.TenantIDContextKey:    uint64(12),
		types.TenantRoleContextKey:  types.TenantRoleAdmin,
		types.SystemAdminContextKey: true,
	}))
	RegisterMaintenanceRoutes(engine, proxy)

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs", nil)
	engine.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusUnauthorized {
		t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
	}
	if !strings.Contains(recorder.Body.String(), `"code":"MAINTENANCE_ACTOR_UNAVAILABLE"`) {
		t.Fatalf("body = %s", recorder.Body.String())
	}
	if upstreamCalls.Load() != 0 {
		t.Fatalf("upstream calls = %d, want 0", upstreamCalls.Load())
	}
}

func TestMaintenanceOptionsDistinguishesCORSPreflightFromOrdinaryRequest(t *testing.T) {
	var resolverCalls atomic.Int32
	secret := []byte(strings.Repeat("m", 32))
	resolver := func(c *gin.Context) (maintenanceproxy.Actor, error) {
		resolverCalls.Add(1)
		return maintenanceproxy.ResolveWebActor(c)
	}
	proxy := newSecurityTestProxy(t, "http://127.0.0.1:8100", newSecurityTestSigner(t, secret), resolver)

	engine := gin.New()
	engine.Use(cors.New(cors.Config{
		AllowOrigins:     []string{"*"},
		AllowMethods:     []string{"GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"},
		AllowHeaders:     []string{"Origin", "Content-Type", "Accept", "Authorization", "X-API-Key", "X-Request-ID", "X-Tenant-ID"},
		AllowCredentials: true,
		MaxAge:           12 * time.Hour,
	}))
	engine.Use(middleware.RequestID())
	engine.Use(middleware.Auth(nil, nil, nil, nil, nil))
	RegisterMaintenanceRoutes(engine, proxy)

	preflightRecorder := httptest.NewRecorder()
	preflight := httptest.NewRequest(http.MethodOptions, "/api/maintenance/jobs", nil)
	preflight.Header.Set("Origin", "https://frontend.example.test")
	preflight.Header.Set("Access-Control-Request-Method", http.MethodGet)
	preflight.Header.Set("Access-Control-Request-Headers", "Authorization")
	engine.ServeHTTP(preflightRecorder, preflight)

	if preflightRecorder.Code != http.StatusNoContent {
		t.Fatalf("preflight status = %d, body = %s", preflightRecorder.Code, preflightRecorder.Body.String())
	}
	if resolverCalls.Load() != 0 {
		t.Fatalf("resolver calls after preflight = %d, want 0", resolverCalls.Load())
	}

	ordinaryRecorder := httptest.NewRecorder()
	ordinary := httptest.NewRequest(http.MethodOptions, "/api/maintenance/jobs", nil)
	engine.ServeHTTP(ordinaryRecorder, ordinary)

	if ordinaryRecorder.Code != http.StatusUnauthorized {
		t.Fatalf("ordinary OPTIONS status = %d, body = %s", ordinaryRecorder.Code, ordinaryRecorder.Body.String())
	}
	if !strings.Contains(ordinaryRecorder.Body.String(), `"code":"MAINTENANCE_ACTOR_UNAVAILABLE"`) {
		t.Fatalf("ordinary OPTIONS body = %s", ordinaryRecorder.Body.String())
	}
	if resolverCalls.Load() != 1 {
		t.Fatalf("resolver calls = %d, want 1", resolverCalls.Load())
	}
}
