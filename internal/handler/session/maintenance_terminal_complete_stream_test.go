package session

import (
	"context"
	"reflect"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
)

type maintenanceTerminalCompleteStreamManager struct {
	events []interfaces.StreamEvent
}

func (m *maintenanceTerminalCompleteStreamManager) AppendEvent(
	ctx context.Context,
	sessionID, messageID string,
	evt interfaces.StreamEvent,
) error {
	m.events = append(m.events, evt)
	return nil
}

func (m *maintenanceTerminalCompleteStreamManager) GetEvents(
	ctx context.Context,
	sessionID, messageID string,
	fromOffset int,
) ([]interfaces.StreamEvent, int, error) {
	if fromOffset >= len(m.events) {
		return nil, len(m.events), nil
	}
	out := append([]interfaces.StreamEvent(nil), m.events[fromOffset:]...)
	return out, len(m.events), nil
}

func TestAppendTerminalCompleteEventCarriesPersistedMaintenanceSnapshotAndReplays(t *testing.T) {
	cards := types.MaintenanceCards{
		{
			SchemaVersion: "1.0",
			Type:          "CALCULATION",
			Title:         "Calculation ready",
			Summary:       "The exact-turn calculation snapshot is ready.",
			Status:        "completed",
			Target: types.MaintenanceCardTarget{
				ObjectType:      "CALCULATION_GROUP",
				ObjectID:        int64(41),
				ObservedVersion: int64(7),
				NavigationPath:  "/platform/maintenance/calculations/41",
			},
			ObservedAt: "2026-08-30T08:00:00Z",
			Payload: map[string]any{
				"scenario": "baseline",
			},
		},
	}

	message := &types.Message{
		ID:               "assistant-b3-terminal-complete",
		SessionID:        "session-b3-terminal-complete",
		Role:             "assistant",
		Content:          "done",
		IsCompleted:      true,
		MaintenanceCards: cards,
		AgentDurationMs:  456,
		AgentSteps:       make([]types.AgentStep, 2),
	}

	streamManager := &maintenanceTerminalCompleteStreamManager{}
	handler := &Handler{
		streamManager: streamManager,
	}

	if err := handler.appendTerminalCompleteEvent(
		context.Background(),
		message,
	); err != nil {
		t.Fatalf("appendTerminalCompleteEvent returned error: %v", err)
	}

	if len(streamManager.events) != 1 {
		t.Fatalf(
			"initial stream event count = %d, want 1",
			len(streamManager.events),
		)
	}

	initial := streamManager.events[0]
	if initial.Type != types.ResponseTypeComplete {
		t.Fatalf(
			"initial event type = %q, want %q",
			initial.Type,
			types.ResponseTypeComplete,
		)
	}
	if !initial.Done {
		t.Fatal("terminal complete event must have Done=true")
	}
	if initial.Content != "" {
		t.Fatalf(
			"terminal complete content = %q, want empty",
			initial.Content,
		)
	}
	if initial.ID == "" {
		t.Fatal("terminal complete event must have a durable event ID")
	}

	gotCards, ok := initial.Data["maintenance_cards"].(types.MaintenanceCards)
	if !ok {
		t.Fatalf(
			"maintenance_cards type = %T, want types.MaintenanceCards",
			initial.Data["maintenance_cards"],
		)
	}
	if !reflect.DeepEqual(gotCards, cards) {
		t.Fatalf(
			"maintenance_cards = %#v, want %#v",
			gotCards,
			cards,
		)
	}
	if got := initial.Data["assistant_message_id"]; got != message.ID {
		t.Fatalf(
			"assistant_message_id = %#v, want %q",
			got,
			message.ID,
		)
	}
	if got := initial.Data["total_duration_ms"]; got != message.AgentDurationMs {
		t.Fatalf(
			"total_duration_ms = %#v, want %d",
			got,
			message.AgentDurationMs,
		)
	}
	if got := initial.Data["total_steps"]; got != len(message.AgentSteps) {
		t.Fatalf(
			"total_steps = %#v, want %d",
			got,
			len(message.AgentSteps),
		)
	}

	replayed, nextOffset, err := streamManager.GetEvents(
		context.Background(),
		message.SessionID,
		message.ID,
		0,
	)
	if err != nil {
		t.Fatalf("GetEvents returned error: %v", err)
	}
	if nextOffset != 1 {
		t.Fatalf("next offset = %d, want 1", nextOffset)
	}
	if len(replayed) != 1 {
		t.Fatalf("replayed event count = %d, want 1", len(replayed))
	}
	if !reflect.DeepEqual(replayed[0], initial) {
		t.Fatalf(
			"replayed terminal event differs from initial event:\ninitial=%#v\nreplayed=%#v",
			initial,
			replayed[0],
		)
	}

}
