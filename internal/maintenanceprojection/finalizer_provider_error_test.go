package maintenanceprojection

import (
	"context"
	"testing"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
)

type providerErrorProjectionClient struct {
	calls int
}

func (c *providerErrorProjectionClient) RecoverExactTurn(
	ctx context.Context,
	actor maintenanceproxy.Actor,
	source types.MaintenanceProjectionProvenance,
) (types.MaintenanceCards, error) {
	c.calls++
	return types.MaintenanceCards{
		{
			SchemaVersion: "1.0",
			Type:          "SCENARIO_DRAFT",
			Title:         "must not be recovered on provider error",
		},
	}, nil
}

type providerErrorTerminalStore struct {
	calls     int
	persisted *types.Message
}

func (s *providerErrorTerminalStore) FinalizeAssistantMessageIfOpen(
	ctx context.Context,
	message *types.Message,
) (bool, error) {
	s.calls++
	cloned := *message
	cloned.MaintenanceCards = append(
		types.MaintenanceCards(nil),
		message.MaintenanceCards...,
	)
	s.persisted = &cloned
	return true, nil
}

func TestTerminalFinalizerProviderErrorClosesMessageWithoutProjectionRecovery(
	t *testing.T,
) {
	client := &providerErrorProjectionClient{}
	store := &providerErrorTerminalStore{}
	finalizer := NewTerminalFinalizer(client, store)

	message := &types.Message{
		ID:          "assistant-provider-error",
		SessionID:   "session-provider-error",
		Role:        "assistant",
		Content:     "partial answer already streamed",
		IsCompleted: false,
		ExecutionContext: types.MessageExecutionContext{
			MaintenanceProjection: &types.MaintenanceProjectionProvenance{
				SchemaVersion:    "1.0",
				SourceKind:       "AI_MESSAGE_TRIGGER",
				AISessionID:      123,
				TriggerMessageID: 456,
			},
		},
		MaintenanceCards: types.MaintenanceCards{
			{
				SchemaVersion: "1.0",
				Type:          "SCENARIO_DRAFT",
				Title:         "stale staged card",
			},
		},
	}

	result, err := finalizer.Finalize(
		context.Background(),
		maintenanceproxy.Actor{},
		message,
		TerminalReasonError,
	)
	if err != nil {
		t.Fatalf("Finalize(error) returned error: %v", err)
	}
	if !result.Persisted {
		t.Fatal("Finalize(error) did not persist terminal message")
	}
	if result.ProjectionError != nil {
		t.Fatalf(
			"Finalize(error) projection error = %v, want nil because recovery must not run",
			result.ProjectionError,
		)
	}
	if client.calls != 0 {
		t.Fatalf(
			"projection client calls = %d, want 0 on provider error",
			client.calls,
		)
	}
	if store.calls != 1 {
		t.Fatalf("terminal store calls = %d, want 1", store.calls)
	}
	if store.persisted == nil {
		t.Fatal("terminal store did not receive message")
	}
	if !store.persisted.IsCompleted {
		t.Fatal("provider-error terminal message was not completed")
	}
	if store.persisted.Content != "partial answer already streamed" {
		t.Fatalf(
			"persisted content = %q, want partial streamed text preserved",
			store.persisted.Content,
		)
	}
	if len(store.persisted.MaintenanceCards) != 0 {
		t.Fatalf(
			"provider-error cards length = %d, want 0",
			len(store.persisted.MaintenanceCards),
		)
	}
	if !message.IsCompleted {
		t.Fatal("original message was not updated after terminal persistence")
	}
	if len(message.MaintenanceCards) != 0 {
		t.Fatalf(
			"original message cards length = %d, want 0",
			len(message.MaintenanceCards),
		)
	}
}
