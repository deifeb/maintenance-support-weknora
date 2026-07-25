package config

import (
	"encoding/json"
	"os"
	"reflect"
	"strings"
	"testing"
	"time"
)

var maintenanceEnvironmentNames = []string{
	"WEKNORA_MAINTENANCE_ENABLED",
	"WEKNORA_MAINTENANCE_BASE_URL",
	"WEKNORA_MAINTENANCE_SIGNING_SECRET",
	"WEKNORA_MAINTENANCE_ISSUER",
	"WEKNORA_MAINTENANCE_AUDIENCE",
	"WEKNORA_MAINTENANCE_TOKEN_TTL",
	"WEKNORA_MAINTENANCE_REQUEST_TIMEOUT",
	"MAINTENANCE_ENABLED",
	"MAINTENANCE_API_BASE_URL",
	"MAINTENANCE_INTERNAL_JWT_SECRET",
	"MAINTENANCE_JWT_ISSUER",
	"MAINTENANCE_JWT_AUDIENCE",
	"MAINTENANCE_JWT_TTL",
	"MAINTENANCE_PROXY_DIAL_TIMEOUT",
}

func clearMaintenanceEnvironment(t *testing.T) {
	t.Helper()

	for _, name := range maintenanceEnvironmentNames {
		value, existed := os.LookupEnv(name)
		if err := os.Unsetenv(name); err != nil {
			t.Fatalf("unset %s: %v", name, err)
		}
		name, value, existed := name, value, existed
		t.Cleanup(func() {
			var err error
			if existed {
				err = os.Setenv(name, value)
			} else {
				err = os.Unsetenv(name)
			}
			if err != nil {
				t.Errorf("restore %s: %v", name, err)
			}
		})
	}
}

func validEnabledMaintenanceConfig() *MaintenanceConfig {
	cfg := DefaultMaintenanceConfig()
	cfg.Enabled = true
	cfg.SigningSecret = strings.Repeat("s", 32)
	return cfg
}

func TestMaintenanceConfigDefaultsMatchPlan(t *testing.T) {
	cfg := DefaultMaintenanceConfig()

	if cfg.Enabled {
		t.Fatal("maintenance proxy must default to disabled")
	}
	if cfg.BaseURL != "http://127.0.0.1:8100" {
		t.Fatalf("BaseURL = %q, want %q", cfg.BaseURL, "http://127.0.0.1:8100")
	}
	if cfg.SigningSecret != "" {
		t.Fatal("SigningSecret must not have a built-in default")
	}
	if cfg.Issuer != "weknora" {
		t.Fatalf("Issuer = %q, want %q", cfg.Issuer, "weknora")
	}
	if cfg.Audience != "maintenance-api" {
		t.Fatalf("Audience = %q, want %q", cfg.Audience, "maintenance-api")
	}
	if cfg.TokenTTL != 180*time.Second {
		t.Fatalf("TokenTTL = %s, want 180s", cfg.TokenTTL)
	}
	if cfg.RequestTimeout != 30*time.Second {
		t.Fatalf("RequestTimeout = %s, want 30s", cfg.RequestTimeout)
	}
}

func TestMaintenanceProxyEnabledIsNilSafe(t *testing.T) {
	cases := []struct {
		name string
		cfg  *Config
		want bool
	}{
		{name: "nil config", cfg: nil, want: false},
		{name: "nil maintenance section", cfg: &Config{}, want: false},
		{name: "disabled", cfg: &Config{Maintenance: &MaintenanceConfig{}}, want: false},
		{name: "enabled", cfg: &Config{Maintenance: &MaintenanceConfig{Enabled: true}}, want: true},
	}

	for _, tc := range cases {
		t.Run(tc.name, func(t *testing.T) {
			if got := MaintenanceProxyEnabled(tc.cfg); got != tc.want {
				t.Fatalf("MaintenanceProxyEnabled() = %v, want %v", got, tc.want)
			}
		})
	}
}

func TestMaintenanceConfigFillsDefaultsForPartialYAML(t *testing.T) {
	clearMaintenanceEnvironment(t)
	t.Setenv("WEKNORA_MAINTENANCE_SIGNING_SECRET", strings.Repeat("x", 32))

	cfg := &Config{Maintenance: &MaintenanceConfig{Enabled: true}}
	if err := applyMaintenanceConfig(cfg); err != nil {
		t.Fatalf("applyMaintenanceConfig() error = %v", err)
	}

	if cfg.Maintenance.BaseURL != "http://127.0.0.1:8100" {
		t.Fatalf("BaseURL = %q", cfg.Maintenance.BaseURL)
	}
	if cfg.Maintenance.Issuer != "weknora" || cfg.Maintenance.Audience != "maintenance-api" {
		t.Fatalf("issuer/audience defaults not filled: %#v", cfg.Maintenance)
	}
	if cfg.Maintenance.TokenTTL != 180*time.Second || cfg.Maintenance.RequestTimeout != 30*time.Second {
		t.Fatalf("duration defaults not filled: %#v", cfg.Maintenance)
	}
}

func TestMaintenanceConfigUsesCanonicalEnvironmentOverrides(t *testing.T) {
	clearMaintenanceEnvironment(t)

	cfg := &Config{Maintenance: &MaintenanceConfig{
		BaseURL:        "http://yaml.example:8100",
		Issuer:         "yaml-issuer",
		Audience:       "yaml-audience",
		TokenTTL:       180 * time.Second,
		RequestTimeout: 10 * time.Second,
	}}

	t.Setenv("MAINTENANCE_ENABLED", "false")
	t.Setenv("MAINTENANCE_API_BASE_URL", "ftp://legacy.example")
	t.Setenv("WEKNORA_MAINTENANCE_ENABLED", "true")
	t.Setenv("WEKNORA_MAINTENANCE_BASE_URL", "https://maintenance.internal:8100")
	t.Setenv("WEKNORA_MAINTENANCE_SIGNING_SECRET", strings.Repeat("k", 32))
	t.Setenv("WEKNORA_MAINTENANCE_ISSUER", "canonical-issuer")
	t.Setenv("WEKNORA_MAINTENANCE_AUDIENCE", "canonical-audience")
	t.Setenv("WEKNORA_MAINTENANCE_TOKEN_TTL", "3m")
	t.Setenv("WEKNORA_MAINTENANCE_REQUEST_TIMEOUT", "45s")

	if err := applyMaintenanceConfig(cfg); err != nil {
		t.Fatalf("applyMaintenanceConfig() error = %v", err)
	}

	got := cfg.Maintenance
	if !got.Enabled || got.BaseURL != "https://maintenance.internal:8100" ||
		got.SigningSecret != strings.Repeat("k", 32) || got.Issuer != "canonical-issuer" ||
		got.Audience != "canonical-audience" || got.TokenTTL != 3*time.Minute ||
		got.RequestTimeout != 45*time.Second {
		t.Fatalf("canonical overrides not applied: %#v", got)
	}
}

func TestMaintenanceConfigRejectsInvalidBooleanEnvironment(t *testing.T) {
	clearMaintenanceEnvironment(t)
	t.Setenv("WEKNORA_MAINTENANCE_ENABLED", "sometimes")

	err := applyMaintenanceConfig(&Config{})
	if err == nil || !strings.Contains(err.Error(), "WEKNORA_MAINTENANCE_ENABLED") {
		t.Fatalf("error = %v, want named invalid boolean error", err)
	}
}

func TestMaintenanceConfigRejectsInvalidDurationEnvironment(t *testing.T) {
	for _, name := range []string{
		"WEKNORA_MAINTENANCE_TOKEN_TTL",
		"WEKNORA_MAINTENANCE_REQUEST_TIMEOUT",
	} {
		t.Run(name, func(t *testing.T) {
			clearMaintenanceEnvironment(t)
			t.Setenv(name, "three minutes")

			err := applyMaintenanceConfig(&Config{})
			if err == nil || !strings.Contains(err.Error(), name) {
				t.Fatalf("error = %v, want named invalid duration error", err)
			}
		})
	}
}

func TestMaintenanceConfigRequiresExactly180SecondTTLWhenEnabled(t *testing.T) {
	for _, ttl := range []time.Duration{179 * time.Second, 181 * time.Second} {
		t.Run(ttl.String(), func(t *testing.T) {
			cfg := validEnabledMaintenanceConfig()
			cfg.TokenTTL = ttl

			err := cfg.Validate()
			if err == nil || !strings.Contains(err.Error(), "180 seconds") {
				t.Fatalf("Validate() error = %v, want exact TTL error", err)
			}
		})
	}
}

func TestMaintenanceConfigRejectsNonHTTPBaseURL(t *testing.T) {
	cases := []string{
		"maintenance.internal:8100",
		"ftp://maintenance.internal:8100",
		"http://user:password@maintenance.internal:8100",
		"http://maintenance.internal:8100?tenant=forged",
		"http://maintenance.internal:8100#fragment",
	}

	for _, baseURL := range cases {
		t.Run(baseURL, func(t *testing.T) {
			cfg := validEnabledMaintenanceConfig()
			cfg.BaseURL = baseURL

			if err := cfg.Validate(); err == nil {
				t.Fatalf("Validate() accepted unsafe BaseURL %q", baseURL)
			}
		})
	}
}

func TestMaintenanceSigningSecretIsNotSerialized(t *testing.T) {
	cfg := validEnabledMaintenanceConfig()
	secret := cfg.SigningSecret

	encoded, err := json.Marshal(cfg)
	if err != nil {
		t.Fatalf("json.Marshal() error = %v", err)
	}
	if strings.Contains(string(encoded), secret) || strings.Contains(string(encoded), "signing_secret") {
		t.Fatalf("JSON leaked signing secret: %s", encoded)
	}

	field, ok := reflect.TypeOf(MaintenanceConfig{}).FieldByName("SigningSecret")
	if !ok {
		t.Fatal("SigningSecret field not found")
	}
	if field.Tag.Get("json") != "-" || field.Tag.Get("yaml") != "-" || field.Tag.Get("mapstructure") != "-" {
		t.Fatalf("SigningSecret serialization tags = %q", string(field.Tag))
	}
}

func TestMaintenanceConfigRejectsShortSecretWhenEnabled(t *testing.T) {
	cfg := DefaultMaintenanceConfig()
	cfg.Enabled = true
	cfg.SigningSecret = "too-short"

	err := cfg.Validate()
	if err == nil || !strings.Contains(err.Error(), "at least 32 bytes") {
		t.Fatalf("Validate() error = %v, want short secret error", err)
	}
}

func TestMaintenanceConfigAcceptsValidEnabledConfig(t *testing.T) {
	if err := validEnabledMaintenanceConfig().Validate(); err != nil {
		t.Fatalf("Validate() error = %v", err)
	}
}
