package config

import (
	"strings"
	"testing"
	"time"

	"github.com/stretchr/testify/require"
)

func TestDefaultMaintenanceConfig(t *testing.T) {
	cfg := DefaultMaintenanceConfig()

	require.False(t, cfg.Enabled)
	require.Equal(t, "http://maintenance-api:8090", cfg.APIBaseURL)
	require.Equal(t, "weknora", cfg.JWTIssuer)
	require.Equal(t, "maintenance-api", cfg.JWTAudience)
	require.Equal(t, 3*time.Minute, cfg.JWTTTL)
	require.Equal(t, 5*time.Second, cfg.ProxyDialTimeout)
}

func TestMaintenanceConfigRejectsShortSecretWhenEnabled(t *testing.T) {
	cfg := DefaultMaintenanceConfig()
	cfg.Enabled = true
	cfg.InternalJWTSecret = "too-short"

	err := cfg.Validate()

	require.ErrorContains(t, err, "at least 32 bytes")
}

func TestMaintenanceConfigAcceptsValidEnabledConfig(t *testing.T) {
	cfg := DefaultMaintenanceConfig()
	cfg.Enabled = true
	cfg.InternalJWTSecret = strings.Repeat("s", 32)

	require.NoError(t, cfg.Validate())
}
