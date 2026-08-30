package session

import (
	"context"
	"testing"
	"time"

	"github.com/Tencent/WeKnora/internal/event"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
)

type agentTerminalOwnershipStreamManager struct {
	events []interfaces.StreamEvent
}

func (m *agentTerminalOwnershipStreamManager) AppendEvent(
	ctx context.Context,
	sessionID, messageID string,
	evt interfaces.StreamEvent,
) error {
	m.events = append(m.events, evt)
	return nil
}

func (m *agentTerminalOwnershipStreamManager) GetEvents(
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

func TestAgentStreamCompleteDoesNotPreemptTerminalFinalizerOwnership(t *testing.T) {
	message := &types.Message{
		ID:          "assistant-agent-terminal-owner",
		SessionID:   "session-agent-terminal-owner",
		Role:        "assistant",
		Content:     "partial ",
		IsCompleted: false,
	}
	streamManager := &agentTerminalOwnershipStreamManager{}
	handler := NewAgentStreamHandler(
		context.Background(),
		message.SessionID,
		message.ID,
		"request-agent-terminal-owner",
		time.Time{},
		message,
		streamManager,
		event.NewEventBus(),
	)
	// Isolate terminal ownership from the fallback-answer safety path.
	// Pretend the final answer has already streamed so handleComplete emits
	// only the single durable complete event under test.
	handler.finalAnswer = "already-streamed"

	err := handler.handleComplete(context.Background(), event.Event{
		ID:        "complete-agent-terminal-owner",
		Type:      event.EventAgentComplete,
		SessionID: message.SessionID,
		Data: event.AgentCompleteData{
			MessageID:       message.ID,
			FinalAnswer:     "answer",
			TotalDurationMs: 321,
			TotalSteps:      2,
		},
	})
	if err != nil {
		t.Fatalf("handleComplete returned error: %v", err)
	}

	if message.IsCompleted {
		t.Fatal(
			"agent stream completion marked the shared message completed; " +
				"terminal finalizer must own IsCompleted",
		)
	}
	if message.AgentDurationMs != 321 {
		t.Fatalf(
			"agent duration = %d, want 321",
			message.AgentDurationMs,
		)
	}
	if message.Content != "partial answer" {
		t.Fatalf(
			"message content = %q, want %q",
			message.Content,
			"partial answer",
		)
	}

	for _, evt := range streamManager.events {
		if evt.Type == types.ResponseTypeComplete {
			t.Fatal(
				"agent stream handler appended ResponseTypeComplete; " +
					"terminal winner must own durable completion event",
			)
		}
	}
}
