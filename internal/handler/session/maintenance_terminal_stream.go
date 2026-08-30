package session

import (
	"context"
	"fmt"
	"time"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
)

// appendTerminalCompleteEvent appends the durable terminal completion snapshot
// for the assistant message that already won terminal persistence.
func (h *Handler) appendTerminalCompleteEvent(
	ctx context.Context,
	message *types.Message,
) error {
	if h == nil || h.streamManager == nil {
		return fmt.Errorf("stream manager is nil")
	}
	if message == nil {
		return fmt.Errorf("assistant message is nil")
	}

	return h.streamManager.AppendEvent(
		ctx,
		message.SessionID,
		message.ID,
		interfaces.StreamEvent{
			ID:        fmt.Sprintf("complete-%d", time.Now().UnixNano()),
			Type:      types.ResponseTypeComplete,
			Content:   "",
			Done:      true,
			Timestamp: time.Now(),
			Data: map[string]interface{}{
				"assistant_message_id": message.ID,
				"total_steps":          len(message.AgentSteps),
				"total_duration_ms":    message.AgentDurationMs,
				"maintenance_cards":    message.MaintenanceCards,
			},
		},
	)
}
