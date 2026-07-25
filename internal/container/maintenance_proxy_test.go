package container

import (
	"strings"
	"testing"
	"time"

	"github.com/Tencent/WeKnora/internal/config"
)

func validMaintenanceConfig() *config.Config {
	maintenance := config.DefaultMaintenanceConfig()
	maintenance.Enabled = true
	maintenance.BaseURL = "http://127.0.0.1:8100"
	maintenance.SigningSecret = strings.Repeat("s", 32)
	maintenance.Issuer = "weknora"
	maintenance.Audience = "maintenance-api"
	maintenance.TokenTTL = 180 * time.Second
	maintenance.RequestTimeout = 30 * time.Second
	return &config.Config{Maintenance: maintenance}
}

func TestNewMaintenanceProxyDisabled(t *testing.T) {
	cfg := &config.Config{Maintenance: &config.MaintenanceConfig{Enabled: false}}

	proxy, err := newMaintenanceProxy(cfg)
	if err != nil {
		t.Fatalf("newMaintenanceProxy() error = %v", err)
	}
	if proxy != nil {
		t.Fatalf("proxy = %#v, want nil", proxy)
	}
}

func TestNewMaintenanceProxyEnabled(t *testing.T) {
	proxy, err := newMaintenanceProxy(validMaintenanceConfig())
	if err != nil {
		t.Fatalf("newMaintenanceProxy() error = %v", err)
	}
	if proxy == nil {
		t.Fatal("proxy is nil")
	}
}
