package router

import (
	"net/http"

	"github.com/gin-gonic/gin"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

// ApplicationHandler applies HTTP behavior that must run outside Gin's router.
type ApplicationHandler struct {
	next                  http.Handler
	rejectBareMaintenance bool
}

// NewApplicationHandler wraps the Gin engine with application-level HTTP rules.
func NewApplicationHandler(engine *gin.Engine, proxy *maintenanceproxy.Proxy) *ApplicationHandler {
	var next http.Handler = engine
	if next == nil {
		next = http.NotFoundHandler()
	}

	return &ApplicationHandler{
		next:                  next,
		rejectBareMaintenance: proxy != nil,
	}
}

// ServeHTTP rejects the bare Maintenance prefix when the proxy is enabled and
// delegates every other request to the Gin engine.
func (handler *ApplicationHandler) ServeHTTP(writer http.ResponseWriter, request *http.Request) {
	if handler.rejectBareMaintenance && request.URL.Path == "/api/maintenance" {
		http.NotFound(writer, request)
		return
	}

	handler.next.ServeHTTP(writer, request)
}
