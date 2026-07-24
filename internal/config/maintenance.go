package config

import (
	"fmt"
	"net/url"
	"os"
	"strconv"
	"strings"
	"time"
)

// MaintenanceConfig controls the private WeKnora-to-Maintenance API
// integration. The signing secret is supplied only through the environment and
// is intentionally excluded from YAML and JSON serialization.
type MaintenanceConfig struct {
	Enabled           bool          `yaml:"enabled" json:"enabled"`
	APIBaseURL        string        `yaml:"api_base_url" json:"api_base_url"`
	InternalJWTSecret string        `yaml:"-" json:"-"`
	JWTIssuer         string        `yaml:"jwt_issuer" json:"jwt_issuer"`
	JWTAudience       string        `yaml:"jwt_audience" json:"jwt_audience"`
	JWTTTL            time.Duration `yaml:"jwt_ttl" json:"jwt_ttl"`
	ProxyDialTimeout  time.Duration `yaml:"proxy_dial_timeout" json:"proxy_dial_timeout"`
}

// DefaultMaintenanceConfig returns safe, disabled-by-default integration
// settings. Enabling the integration requires a secret of at least 32 bytes.
func DefaultMaintenanceConfig() *MaintenanceConfig {
	return &MaintenanceConfig{
		Enabled:          false,
		APIBaseURL:       "http://maintenance-api:8090",
		JWTIssuer:        "weknora",
		JWTAudience:      "maintenance-api",
		JWTTTL:           3 * time.Minute,
		ProxyDialTimeout: 5 * time.Second,
	}
}

// Validate rejects incomplete or unsafe enabled-mode settings. Disabled mode
// remains compatible with existing WeKnora deployments.
func (c *MaintenanceConfig) Validate() error {
	if c == nil || !c.Enabled {
		return nil
	}

	parsed, err := url.Parse(c.APIBaseURL)
	if err != nil || parsed.Scheme == "" || parsed.Host == "" {
		return fmt.Errorf("maintenance api_base_url must be an absolute URL")
	}
	if len([]byte(c.InternalJWTSecret)) < 32 {
		return fmt.Errorf("maintenance internal JWT secret must contain at least 32 bytes")
	}
	if strings.TrimSpace(c.JWTIssuer) == "" || strings.TrimSpace(c.JWTAudience) == "" {
		return fmt.Errorf("maintenance JWT issuer and audience are required")
	}
	if c.JWTTTL <= 0 || c.ProxyDialTimeout <= 0 {
		return fmt.Errorf("maintenance JWT TTL and proxy timeout must be positive")
	}
	return nil
}

func applyMaintenanceEnv(cfg *Config) error {
	if cfg.Maintenance == nil {
		cfg.Maintenance = DefaultMaintenanceConfig()
	}

	readBoolEnv("MAINTENANCE_ENABLED", &cfg.Maintenance.Enabled)
	readStringEnv("MAINTENANCE_API_BASE_URL", &cfg.Maintenance.APIBaseURL)
	readStringEnv("MAINTENANCE_INTERNAL_JWT_SECRET", &cfg.Maintenance.InternalJWTSecret)
	readStringEnv("MAINTENANCE_JWT_ISSUER", &cfg.Maintenance.JWTIssuer)
	readStringEnv("MAINTENANCE_JWT_AUDIENCE", &cfg.Maintenance.JWTAudience)
	readDurationEnv("MAINTENANCE_JWT_TTL", &cfg.Maintenance.JWTTTL)
	readDurationEnv("MAINTENANCE_PROXY_DIAL_TIMEOUT", &cfg.Maintenance.ProxyDialTimeout)

	return cfg.Maintenance.Validate()
}

func readStringEnv(name string, target *string) {
	if value, ok := os.LookupEnv(name); ok {
		*target = strings.TrimSpace(value)
	}
}

func readBoolEnv(name string, target *bool) {
	if value, ok := os.LookupEnv(name); ok {
		if parsed, err := strconv.ParseBool(strings.TrimSpace(value)); err == nil {
			*target = parsed
		}
	}
}

func readDurationEnv(name string, target *time.Duration) {
	if value, ok := os.LookupEnv(name); ok {
		if parsed, err := time.ParseDuration(strings.TrimSpace(value)); err == nil {
			*target = parsed
		}
	}
}
