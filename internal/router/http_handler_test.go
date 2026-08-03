package router

import (
	"net/http"
	"net/http/httptest"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

func TestApplicationHandlerRejectsBareMaintenancePathWhenProxyEnabled(t *testing.T) {
	engine := gin.New()
	engine.GET("/api/maintenance/*path", func(c *gin.Context) {
		c.Status(http.StatusNoContent)
	})
	handler := NewApplicationHandler(engine, new(maintenanceproxy.Proxy))

	for _, target := range []string{
		"/api/maintenance",
		"/api/maintenance?view=summary",
	} {
		t.Run(target, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			request := httptest.NewRequest(http.MethodGet, target, nil)

			handler.ServeHTTP(recorder, request)

			if recorder.Code != http.StatusNotFound {
				t.Fatalf("status = %d, want 404", recorder.Code)
			}
			if location := recorder.Header().Get("Location"); location != "" {
				t.Fatalf("Location = %q, want empty", location)
			}
		})
	}
}

func TestApplicationHandlerDelegatesMaintenanceDescendants(t *testing.T) {
	engine := gin.New()
	engine.GET("/api/maintenance/*path", func(c *gin.Context) {
		c.Status(http.StatusNoContent)
	})
	handler := NewApplicationHandler(engine, new(maintenanceproxy.Proxy))

	for _, target := range []string{
		"/api/maintenance/",
		"/api/maintenance/jobs",
	} {
		t.Run(target, func(t *testing.T) {
			recorder := httptest.NewRecorder()
			request := httptest.NewRequest(http.MethodGet, target, nil)

			handler.ServeHTTP(recorder, request)

			if recorder.Code != http.StatusNoContent {
				t.Fatalf("status = %d, want 204", recorder.Code)
			}
		})
	}
}

func TestApplicationHandlerDelegatesWhenProxyDisabled(t *testing.T) {
	engine := gin.New()
	engine.GET("/api/maintenance", func(c *gin.Context) {
		c.Status(http.StatusNoContent)
	})
	handler := NewApplicationHandler(engine, nil)

	recorder := httptest.NewRecorder()
	request := httptest.NewRequest(http.MethodGet, "/api/maintenance", nil)
	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNoContent {
		t.Fatalf("status = %d, want 204", recorder.Code)
	}
}
