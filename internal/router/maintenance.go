package router

import (
	"github.com/gin-gonic/gin"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

// RegisterMaintenanceRoutes registers the authenticated Maintenance proxy route
// when the optional proxy dependency is available.
func RegisterMaintenanceRoutes(engine *gin.Engine, proxy *maintenanceproxy.Proxy) {
	if engine == nil || proxy == nil {
		return
	}
	engine.Any("/api/maintenance/*path", proxy.ServeHTTP)
}
