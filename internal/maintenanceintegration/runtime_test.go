package maintenanceintegration

import (
	"context"
	"testing"

	"github.com/Tencent/WeKnora/internal/config"
	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
)

type fakeRuntimeMessageService struct {
	interfaces.MessageService
	finalizeCalls int
}

func (s *fakeRuntimeMessageService) FinalizeAssistantMessageIfOpen(
	ctx context.Context,
	message *types.Message,
) (bool, error) {
	s.finalizeCalls++
	return true, nil
}

func disabledRuntimeConfig() *config.Config {
	return &config.Config{
		Maintenance: config.DefaultMaintenanceConfig(),
	}
}

func enabledRuntimeConfig() *config.Config {
	maintenance := config.DefaultMaintenanceConfig()
	maintenance.Enabled = true
	maintenance.SigningSecret = "0123456789abcdef0123456789abcdef"
	return &config.Config{
		Maintenance: maintenance,
	}
}

func TestNewRuntimeKeepsOrdinaryTerminalPersistenceWhenMaintenanceDisabled(
	t *testing.T,
) {
	messageService := &fakeRuntimeMessageService{}

	runtime, err := NewRuntime(
		disabledRuntimeConfig(),
		messageService,
	)
	if err != nil {
		t.Fatalf("NewRuntime() error = %v", err)
	}
	if runtime == nil {
		t.Fatal("NewRuntime() = nil")
	}
	if runtime.Proxy != nil {
		t.Fatal("disabled runtime Proxy != nil")
	}
	if runtime.Client != nil {
		t.Fatal("disabled runtime Client != nil")
	}
	if runtime.Finalizer == nil {
		t.Fatal("disabled runtime Finalizer = nil")
	}

	message := &types.Message{
		ID:        "assistant-disabled",
		SessionID: "session-disabled",
		Role:      "assistant",
		Content:   "ordinary chat text",
	}
	result, err := runtime.Finalizer.Finalize(
		context.Background(),
		maintenanceproxy.Actor{},
		message,
		maintenanceprojection.TerminalReasonNormal,
	)
	if err != nil {
		t.Fatalf("Finalize() error = %v", err)
	}
	if !result.Persisted {
		t.Fatal("Finalize() Persisted = false, want true")
	}
	if result.ProjectionError != nil {
		t.Fatalf(
			"ordinary disabled projection error = %v, want nil",
			result.ProjectionError,
		)
	}
	if messageService.finalizeCalls != 1 {
		t.Fatalf(
			"terminal store calls = %d, want 1",
			messageService.finalizeCalls,
		)
	}
	if !message.IsCompleted {
		t.Fatal("ordinary disabled message IsCompleted = false")
	}
}

func TestNewRuntimeBuildsProxyClientAndFinalizerFromOneEnabledConfiguration(
	t *testing.T,
) {
	runtime, err := NewRuntime(
		enabledRuntimeConfig(),
		&fakeRuntimeMessageService{},
	)
	if err != nil {
		t.Fatalf("NewRuntime() error = %v", err)
	}
	if runtime == nil {
		t.Fatal("NewRuntime() = nil")
	}
	if runtime.Proxy == nil {
		t.Fatal("enabled runtime Proxy = nil")
	}
	if runtime.Client == nil {
		t.Fatal("enabled runtime Client = nil")
	}
	if runtime.Finalizer == nil {
		t.Fatal("enabled runtime Finalizer = nil")
	}
}

func TestNewRuntimeRejectsUnsafeEnabledMaintenanceConfiguration(
	t *testing.T,
) {
	cfg := enabledRuntimeConfig()
	cfg.Maintenance.SigningSecret = "short"

	runtime, err := NewRuntime(
		cfg,
		&fakeRuntimeMessageService{},
	)
	if err == nil {
		t.Fatal("NewRuntime() error = nil, want configuration failure")
	}
	if runtime != nil {
		t.Fatalf("NewRuntime() = %#v, want nil on configuration failure", runtime)
	}
}
