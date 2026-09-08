package maintenanceintegration

import (
	"errors"
	"fmt"

	"github.com/Tencent/WeKnora/internal/config"
	"github.com/Tencent/WeKnora/internal/maintenanceclient"
	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
)

// Runtime groups the Maintenance components that must share one validated
// configuration and, when enabled, one internal-token signer.
type Runtime struct {
	Proxy     *maintenanceproxy.Proxy
	Client    *maintenanceclient.Client
	Finalizer *maintenanceprojection.TerminalFinalizer
}

// ProxyFromRuntime exposes the exact browser proxy instance built by Runtime
// for dependency injection.
func ProxyFromRuntime(runtime *Runtime) *maintenanceproxy.Proxy {
	if runtime == nil {
		return nil
	}
	return runtime.Proxy
}

// FinalizerFromRuntime exposes the exact terminal finalizer instance built by
// Runtime for dependency injection into the session handler.
func FinalizerFromRuntime(runtime *Runtime) *maintenanceprojection.TerminalFinalizer {
	if runtime == nil {
		return nil
	}
	return runtime.Finalizer
}

// NewRuntime builds the Maintenance integration used by the Core runtime.
// Terminal finalization is always available so ordinary chat completion keeps
// using the conditional terminal write even when Maintenance projection is
// disabled. Proxy and exact-turn client are created only when Maintenance is
// enabled.
func NewRuntime(
	cfg *config.Config,
	messageService interfaces.MessageService,
) (*Runtime, error) {
	if cfg == nil {
		return nil, errors.New("maintenance runtime config is nil")
	}

	maintenanceCfg := cfg.Maintenance
	if maintenanceCfg == nil {
		maintenanceCfg = config.DefaultMaintenanceConfig()
	}

	if err := maintenanceCfg.Validate(); err != nil {
		return nil, fmt.Errorf("validate maintenance runtime config: %w", err)
	}

	runtime := &Runtime{
		Finalizer: maintenanceprojection.NewTerminalFinalizer(
			nil,
			messageService,
		),
	}

	if !maintenanceCfg.Enabled {
		return runtime, nil
	}

	signer, err := maintenanceproxy.NewSigner(
		[]byte(maintenanceCfg.SigningSecret),
		maintenanceCfg.Issuer,
		maintenanceCfg.Audience,
		maintenanceCfg.TokenTTL,
	)
	if err != nil {
		return nil, fmt.Errorf("create maintenance runtime signer: %w", err)
	}

	proxy, err := maintenanceproxy.New(
		maintenanceCfg.BaseURL,
		signer,
		maintenanceproxy.ResolveWebActor,
		maintenanceCfg.RequestTimeout,
	)
	if err != nil {
		return nil, fmt.Errorf("create maintenance runtime proxy: %w", err)
	}

	client, err := maintenanceclient.New(maintenanceCfg, signer)
	if err != nil {
		return nil, fmt.Errorf("create maintenance runtime client: %w", err)
	}

	runtime.Proxy = proxy
	runtime.Client = client
	runtime.Finalizer = maintenanceprojection.NewTerminalFinalizer(
		client,
		messageService,
	)
	return runtime, nil
}
