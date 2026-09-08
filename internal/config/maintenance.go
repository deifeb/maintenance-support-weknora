package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

const (
	maintenanceInternalTokenTTL     = 180 * time.Second
	maintenanceExampleSigningSecret = "replace-with-at-least-32-random-bytes"
)

// MaintenanceConfig controls the private WeKnora-to-Maintenance API
// integration. SigningSecret is supplied only through the environment and is
// intentionally excluded from YAML, JSON, and mapstructure decoding.
type MaintenanceConfig struct {
	Enabled        bool          `yaml:"enabled" json:"enabled"`
	BaseURL        string        `yaml:"base_url" json:"base_url"`
	SigningSecret  string        `yaml:"-" json:"-" mapstructure:"-"`
	Issuer         string        `yaml:"issuer" json:"issuer"`
	Audience       string        `yaml:"audience" json:"audience"`
	TokenTTL       time.Duration `yaml:"token_ttl" json:"token_ttl"`
	RequestTimeout time.Duration `yaml:"request_timeout" json:"request_timeout"`
}

// DefaultMaintenanceConfig returns safe, disabled-by-default integration
// settings. Docker deployments override BaseURL through the canonical
// WEKNORA_MAINTENANCE_BASE_URL environment variable.
func DefaultMaintenanceConfig() *MaintenanceConfig {
	return &MaintenanceConfig{
		Enabled:        false,
		BaseURL:        "http://127.0.0.1:8100",
		Issuer:         "weknora",
		Audience:       "maintenance-api",
		TokenTTL:       maintenanceInternalTokenTTL,
		RequestTimeout: 30 * time.Second,
	}
}

// MaintenanceProxyEnabled reports whether the private maintenance proxy is
// configured. It is deliberately nil-safe because existing deployments may
// omit the maintenance section entirely.
func MaintenanceProxyEnabled(cfg *Config) bool {
	return cfg != nil && cfg.Maintenance != nil && cfg.Maintenance.Enabled
}

// Validate rejects incomplete or unsafe settings. Disabled mode does not
// require a signing secret, but all other supplied connection settings must be
// structurally valid so enabling the feature cannot expose a latent bad value.
func (c *MaintenanceConfig) Validate() error {
	if c == nil {
		return nil
	}

	parsed, err := url.Parse(c.BaseURL)
	if err != nil || parsed.Opaque != "" || parsed.Hostname() == "" {
		return fmt.Errorf("maintenance base_url must be an absolute HTTP(S) URL")
	}
	scheme := strings.ToLower(parsed.Scheme)
	if scheme != "http" && scheme != "https" {
		return fmt.Errorf("maintenance base_url must use http or https")
	}
	if parsed.User != nil || parsed.RawQuery != "" || parsed.ForceQuery || parsed.Fragment != "" {
		return fmt.Errorf("maintenance base_url must not contain userinfo, query, or fragment")
	}
	if strings.TrimSpace(c.Issuer) == "" || strings.TrimSpace(c.Audience) == "" {
		return fmt.Errorf("maintenance issuer and audience are required")
	}
	if c.TokenTTL <= 0 {
		return fmt.Errorf("maintenance token_ttl must be positive")
	}
	if c.RequestTimeout <= 0 {
		return fmt.Errorf("maintenance request_timeout must be positive")
	}

	if !c.Enabled {
		return nil
	}
	if c.TokenTTL != maintenanceInternalTokenTTL {
		return fmt.Errorf("maintenance token_ttl must be exactly 180 seconds when enabled")
	}
	signingSecret := strings.TrimSpace(c.SigningSecret)
	if signingSecret == maintenanceExampleSigningSecret {
		return fmt.Errorf("maintenance signing secret must be replaced before enabling the proxy")
	}
	if len([]byte(signingSecret)) < 32 {
		return fmt.Errorf("maintenance signing secret must contain at least 32 bytes")
	}
	return nil
}

// applyMaintenanceConfig resolves configuration in strict precedence order:
// built-in defaults, non-zero YAML values, then canonical environment
// overrides. Invalid environment values fail startup rather than being ignored.
func applyMaintenanceConfig(cfg *Config) error {
	if cfg == nil {
		return fmt.Errorf("maintenance root config must not be nil")
	}

	resolved := DefaultMaintenanceConfig()
	mergeMaintenanceYAML(resolved, cfg.Maintenance)

	if err := overrideMaintenanceBoolEnv("WEKNORA_MAINTENANCE_ENABLED", &resolved.Enabled); err != nil {
		return err
	}
	overrideMaintenanceStringEnv("WEKNORA_MAINTENANCE_BASE_URL", &resolved.BaseURL)
	overrideMaintenanceStringEnv("WEKNORA_MAINTENANCE_SIGNING_SECRET", &resolved.SigningSecret)
	overrideMaintenanceStringEnv("WEKNORA_MAINTENANCE_ISSUER", &resolved.Issuer)
	overrideMaintenanceStringEnv("WEKNORA_MAINTENANCE_AUDIENCE", &resolved.Audience)
	if err := overrideMaintenanceDurationEnv("WEKNORA_MAINTENANCE_TOKEN_TTL", &resolved.TokenTTL); err != nil {
		return err
	}
	if err := overrideMaintenanceDurationEnv("WEKNORA_MAINTENANCE_REQUEST_TIMEOUT", &resolved.RequestTimeout); err != nil {
		return err
	}

	cfg.Maintenance = resolved
	return resolved.Validate()
}

func mergeMaintenanceYAML(target, source *MaintenanceConfig) {
	if source == nil {
		return
	}

	target.Enabled = source.Enabled
	if value := strings.TrimSpace(source.BaseURL); value != "" {
		target.BaseURL = value
	}
	if value := strings.TrimSpace(source.Issuer); value != "" {
		target.Issuer = value
	}
	if value := strings.TrimSpace(source.Audience); value != "" {
		target.Audience = value
	}
	if source.TokenTTL != 0 {
		target.TokenTTL = source.TokenTTL
	}
	if source.RequestTimeout != 0 {
		target.RequestTimeout = source.RequestTimeout
	}
}

func overrideMaintenanceStringEnv(name string, target *string) {
	if value, ok := os.LookupEnv(name); ok {
		*target = strings.TrimSpace(value)
	}
}

func overrideMaintenanceBoolEnv(name string, target *bool) error {
	value, ok := os.LookupEnv(name)
	if !ok {
		return nil
	}

	parsed, err := strconv.ParseBool(strings.TrimSpace(value))
	if err != nil {
		return fmt.Errorf("%s must be a boolean: %w", name, err)
	}
	*target = parsed
	return nil
}

func overrideMaintenanceDurationEnv(name string, target *time.Duration) error {
	value, ok := os.LookupEnv(name)
	if !ok {
		return nil
	}

	parsed, err := time.ParseDuration(strings.TrimSpace(value))
	if err != nil {
		return fmt.Errorf("%s must be a duration: %w", name, err)
	}
	if parsed <= 0 {
		return fmt.Errorf("%s must be a positive duration", name)
	}
	*target = parsed
	return nil
}
