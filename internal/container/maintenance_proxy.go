package container

import (
	"errors"
	"fmt"

	"github.com/Tencent/WeKnora/internal/config"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

func newMaintenanceProxy(cfg *config.Config) (*maintenanceproxy.Proxy, error) {
	if cfg == nil {
		return nil, errors.New("maintenance proxy config is nil")
	}
	if !config.MaintenanceProxyEnabled(cfg) {
		return nil, nil
	}

	if err := cfg.Maintenance.Validate(); err != nil {
		return nil, fmt.Errorf("validate maintenance proxy config: %w", err)
	}

	signer, err := maintenanceproxy.NewSigner(
		[]byte(cfg.Maintenance.SigningSecret),
		cfg.Maintenance.Issuer,
		cfg.Maintenance.Audience,
		cfg.Maintenance.TokenTTL,
	)
	if err != nil {
		return nil, fmt.Errorf("create maintenance signer: %w", err)
	}

	proxy, err := maintenanceproxy.New(
		cfg.Maintenance.BaseURL,
		signer,
		maintenanceproxy.ResolveWebActor,
		cfg.Maintenance.RequestTimeout,
	)
	if err != nil {
		return nil, fmt.Errorf("create maintenance proxy: %w", err)
	}
	return proxy, nil
}
