package router

import (
	"io"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"
	"time"

	"github.com/gin-gonic/gin"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

type routerTestResponseWriter struct {
	*httptest.ResponseRecorder
}

func (writer *routerTestResponseWriter) CloseNotify() <-chan bool {
	return make(chan bool)
}

func newRouterTestProxy(t *testing.T, upstreamURL string) *maintenanceproxy.Proxy {
	t.Helper()

	signer, err := maintenanceproxy.NewSigner(
		[]byte(strings.Repeat("s", 32)),
		"weknora",
		"maintenance-api",
		180*time.Second,
	)
	if err != nil {
		t.Fatalf("NewSigner() error = %v", err)
	}

	proxy, err := maintenanceproxy.New(
		upstreamURL,
		signer,
		func(*gin.Context) (maintenanceproxy.Actor, error) {
			return maintenanceproxy.Actor{
				UserID:    "user-1",
				TenantID:  "12",
				Roles:     []string{"viewer"},
				RequestID: "req-route",
			}, nil
		},
		5*time.Second,
	)
	if err != nil {
		t.Fatalf("maintenanceproxy.New() error = %v", err)
	}
	return proxy
}

func TestRegisterMaintenanceRoutesDisabled(t *testing.T) {
	engine := gin.New()
	RegisterMaintenanceRoutes(engine, nil)

	for _, route := range engine.Routes() {
		if route.Path == "/api/maintenance/*path" {
			t.Fatalf("unexpected Maintenance route: %#v", route)
		}
	}

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/maintenance/", nil)
	engine.ServeHTTP(recorder, request)
	if recorder.Code != http.StatusNotFound {
		t.Fatalf("status = %d, want 404", recorder.Code)
	}
}

func TestRegisterMaintenanceRoutesForwardsPathAndQuery(t *testing.T) {
	received := make(chan string, 1)
	upstream := httptest.NewServer(http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		received <- request.URL.RequestURI()
		writer.Header().Set("Content-Type", "application/json")
		_, _ = io.WriteString(writer, `{"ok":true}`)
	}))
	defer upstream.Close()

	engine := gin.New()
	RegisterMaintenanceRoutes(engine, newRouterTestProxy(t, upstream.URL))

	recorder := httptest.NewRecorder()
	writer := &routerTestResponseWriter{ResponseRecorder: recorder}
	request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs?page=2", nil)
	engine.ServeHTTP(writer, request)

	if recorder.Code != http.StatusOK {
		t.Fatalf("status = %d, body = %s", recorder.Code, recorder.Body.String())
	}
	if uri := <-received; uri != "/api/jobs?page=2" {
		t.Fatalf("upstream URI = %q, want /api/jobs?page=2", uri)
	}
}
