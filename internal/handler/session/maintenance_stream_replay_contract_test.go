package session

import (
	"context"
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
	"github.com/gin-gonic/gin"
)

func TestReplayBuildStreamResponsePreservesMaintenanceCardsSnapshot(t *testing.T) {
	cards := types.MaintenanceCards{
		{
			SchemaVersion: "1.0",
			Type:          "REVIEW_FINDING",
			Title:         "Review finding",
			Summary:       "Exact persisted snapshot.",
			Status:        "open",
			Target: types.MaintenanceCardTarget{
				ObjectType:      "DEMAND_REVIEW_FINDING",
				ObjectID:        int64(73),
				ObservedVersion: int64(4),
				NavigationPath:  "/platform/maintenance/review-findings/73",
			},
			ObservedAt: "2026-08-30T09:15:00Z",
			Payload: map[string]any{
				"severity": "high",
			},
		},
	}

	manager := &maintenanceTerminalCompleteStreamManager{}
	original := interfaces.StreamEvent{
		ID:      "complete-b3-replay",
		Type:    types.ResponseTypeComplete,
		Content: "",
		Done:    true,
		Data: map[string]interface{}{
			"assistant_message_id": "assistant-b3-replay",
			"total_steps":          3,
			"total_duration_ms":    int64(812),
			"maintenance_cards":    cards,
		},
	}

	if err := manager.AppendEvent(
		context.Background(),
		"session-b3-replay",
		"assistant-b3-replay",
		original,
	); err != nil {
		t.Fatalf("AppendEvent returned error: %v", err)
	}

	replayed, nextOffset, err := manager.GetEvents(
		context.Background(),
		"session-b3-replay",
		"assistant-b3-replay",
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

	response := buildStreamResponse(replayed[0], "request-b3-replay")
	if response.ResponseType != types.ResponseTypeComplete {
		t.Fatalf(
			"response type = %q, want %q",
			response.ResponseType,
			types.ResponseTypeComplete,
		)
	}
	if !response.Done {
		t.Fatal("replayed complete response must have Done=true")
	}
	if !reflect.DeepEqual(response.Data, original.Data) {
		t.Fatalf(
			"replayed response data changed:\noriginal=%#v\nresponse=%#v",
			original.Data,
			response.Data,
		)
	}

	gotCards, ok := response.Data["maintenance_cards"].(types.MaintenanceCards)
	if !ok {
		t.Fatalf(
			"maintenance_cards type = %T, want types.MaintenanceCards",
			response.Data["maintenance_cards"],
		)
	}
	if !reflect.DeepEqual(gotCards, cards) {
		t.Fatalf(
			"maintenance_cards = %#v, want %#v",
			gotCards,
			cards,
		)
	}
}

func TestSendCompletionEventEmitsNoSyntheticTerminalResponse(t *testing.T) {
	gin.SetMode(gin.TestMode)

	recorder := httptest.NewRecorder()
	ctx, _ := gin.CreateTestContext(recorder)

	sendCompletionEvent(ctx, "request-b3-no-duplicate")

	if recorder.Body.Len() != 0 {
		t.Fatalf(
			"sendCompletionEvent emitted synthetic response body %q, want empty",
			recorder.Body.String(),
		)
	}
}
