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

func TestNewMaintenanceProxyRejectsInvalidEnabledConfig(t *testing.T) {
	tests := []struct {
		name       string
		mutate     func(*config.Config)
		errorMatch string
	}{
		{
			name: "short secret",
			mutate: func(cfg *config.Config) {
				cfg.Maintenance.SigningSecret = "short"
			},
			errorMatch: "signing secret",
		},
		{
			name: "blank issuer",
			mutate: func(cfg *config.Config) {
				cfg.Maintenance.Issuer = " "
			},
			errorMatch: "issuer and audience",
		},
		{
			name: "blank audience",
			mutate: func(cfg *config.Config) {
				cfg.Maintenance.Audience = " "
			},
			errorMatch: "issuer and audience",
		},
		{
			name: "wrong token ttl",
			mutate: func(cfg *config.Config) {
				cfg.Maintenance.TokenTTL = 179 * time.Second
			},
			errorMatch: "exactly 180 seconds",
		},
		{
			name: "zero request timeout",
			mutate: func(cfg *config.Config) {
				cfg.Maintenance.RequestTimeout = 0
			},
			errorMatch: "request_timeout",
		},
		{
			name: "relative base url",
			mutate: func(cfg *config.Config) {
				cfg.Maintenance.BaseURL = "/maintenance"
			},
			errorMatch: "absolute HTTP(S) URL",
		},
		{
			name: "service path base url",
			mutate: func(cfg *config.Config) {
				cfg.Maintenance.BaseURL = "http://127.0.0.1:8100/service"
			},
			errorMatch: "service root",
		},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			cfg := validMaintenanceConfig()
			test.mutate(cfg)

			proxy, err := newMaintenanceProxy(cfg)
			if err == nil {
				t.Fatal("newMaintenanceProxy() error is nil")
			}
			if proxy != nil {
				t.Fatalf("proxy = %#v, want nil", proxy)
			}
			if !strings.Contains(err.Error(), test.errorMatch) {
				t.Fatalf("error = %q, want substring %q", err.Error(), test.errorMatch)
			}
		})
	}
}

func TestNewMaintenanceProxyRejectsNilConfig(t *testing.T) {
	proxy, err := newMaintenanceProxy(nil)
	if err == nil {
		t.Fatal("newMaintenanceProxy(nil) error is nil")
	}
	if proxy != nil {
		t.Fatalf("proxy = %#v, want nil", proxy)
	}
}
