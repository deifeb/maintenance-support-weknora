package session

import (
	"context"
	"reflect"
	"sync"
	"testing"
	"time"

	"github.com/Tencent/WeKnora/internal/event"
	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
)

type recordingTerminalCallsiteMessageService struct {
	interfaces.MessageService

	mu          sync.Mutex
	updateCalls int
	indexCalls  int
	indexed     chan struct{}
}

func newRecordingTerminalCallsiteMessageService() *recordingTerminalCallsiteMessageService {
	return &recordingTerminalCallsiteMessageService{
		indexed: make(chan struct{}, 8),
	}
}

func (s *recordingTerminalCallsiteMessageService) UpdateMessage(
	ctx context.Context,
	message *types.Message,
) error {
	s.mu.Lock()
	s.updateCalls++
	s.mu.Unlock()
	return nil
}

func (s *recordingTerminalCallsiteMessageService) IndexMessageToKB(
	ctx context.Context,
	query string,
	answer string,
	messageID string,
	sessionID string,
) {
	s.mu.Lock()
	s.indexCalls++
	s.mu.Unlock()

	select {
	case s.indexed <- struct{}{}:
	default:
	}
}

func (s *recordingTerminalCallsiteMessageService) counts() (int, int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return s.updateCalls, s.indexCalls
}

type recordingTerminalCallsiteFinalizer struct {
	calls  int
	actor  maintenanceproxy.Actor
	reason maintenanceprojection.TerminalReason
	msg    *types.Message
	result maintenanceprojection.TerminalFinalizeResult
	err    error
}

func (f *recordingTerminalCallsiteFinalizer) Finalize(
	ctx context.Context,
	actor maintenanceproxy.Actor,
	message *types.Message,
	reason maintenanceprojection.TerminalReason,
) (maintenanceprojection.TerminalFinalizeResult, error) {
	f.calls++
	f.actor = actor
	f.reason = reason
	f.msg = message
	return f.result, f.err
}

func terminalCallsiteAssistant() *types.Message {
	return &types.Message{
		ID:        "assistant-callsite-1",
		SessionID: "session-callsite-1",
		Role:      "assistant",
		Content:   "final assistant text",
		ExecutionContext: types.MessageExecutionContext{
			MaintenanceProjection: &types.MaintenanceProjectionProvenance{
				SchemaVersion:    "1.0",
				SourceKind:       "AI_MESSAGE_TRIGGER",
				AISessionID:      123,
				TriggerMessageID: 456,
			},
		},
	}
}

func terminalCallsiteActorContext() context.Context {
	ctx := context.Background()
	ctx = context.WithValue(
		ctx,
		types.RequestIDContextKey,
		"req-callsite-1",
	)
	ctx = context.WithValue(
		ctx,
		types.PrincipalContextKey,
		types.Principal{
			Type: types.PrincipalWebUser,
			ID:   "user-1",
		},
	)
	ctx = context.WithValue(
		ctx,
		types.UserIDContextKey,
		"user-1",
	)
	ctx = context.WithValue(
		ctx,
		types.TenantIDContextKey,
		uint64(12),
	)
	ctx = context.WithValue(
		ctx,
		types.TenantRoleContextKey,
		types.TenantRoleContributor,
	)
	ctx = context.WithValue(
		ctx,
		types.SystemAdminContextKey,
		false,
	)
	return ctx
}

func TestCompleteAssistantMessageRoutesNormalAndAgentCallsitesThroughTerminalFinalizer(
	t *testing.T,
) {
	messageService := newRecordingTerminalCallsiteMessageService()
	finalizer := &recordingTerminalCallsiteFinalizer{
		result: maintenanceprojection.TerminalFinalizeResult{
			Persisted: true,
		},
	}
	handler := &Handler{
		messageService:               messageService,
		maintenanceTerminalFinalizer: finalizer,
	}
	message := terminalCallsiteAssistant()

	handler.completeAssistantMessage(
		terminalCallsiteActorContext(),
		message,
		"user question",
	)

	if finalizer.calls != 1 {
		t.Fatalf("terminal finalizer calls = %d, want 1", finalizer.calls)
	}
	if finalizer.reason != maintenanceprojection.TerminalReasonNormal {
		t.Fatalf(
			"terminal reason = %q, want %q",
			finalizer.reason,
			maintenanceprojection.TerminalReasonNormal,
		)
	}
	if finalizer.msg != message {
		t.Fatal("terminal finalizer did not receive exact assistant message")
	}

	updateCalls, _ := messageService.counts()
	if updateCalls != 0 {
		t.Fatalf(
			"legacy UpdateMessage calls = %d, want 0",
			updateCalls,
		)
	}
}

func TestCompleteAssistantMessageDoesNotPostProcessWhenTerminalRaceWasLost(
	t *testing.T,
) {
	messageService := newRecordingTerminalCallsiteMessageService()
	finalizer := &recordingTerminalCallsiteFinalizer{
		result: maintenanceprojection.TerminalFinalizeResult{
			Persisted: false,
		},
	}
	handler := &Handler{
		messageService:               messageService,
		maintenanceTerminalFinalizer: finalizer,
	}

	handler.completeAssistantMessage(
		terminalCallsiteActorContext(),
		terminalCallsiteAssistant(),
		"user question",
	)

	select {
	case <-messageService.indexed:
		t.Fatal("losing terminal path must not index assistant message")
	case <-time.After(75 * time.Millisecond):
	}

	updateCalls, indexCalls := messageService.counts()
	if updateCalls != 0 {
		t.Fatalf(
			"legacy UpdateMessage calls = %d, want 0",
			updateCalls,
		)
	}
	if indexCalls != 0 {
		t.Fatalf(
			"index calls = %d, want 0 after losing terminal race",
			indexCalls,
		)
	}
}

func TestSetupStopEventHandlerUsesStopTerminalFinalization(
	t *testing.T,
) {
	messageService := newRecordingTerminalCallsiteMessageService()
	finalizer := &recordingTerminalCallsiteFinalizer{
		result: maintenanceprojection.TerminalFinalizeResult{
			Persisted: true,
		},
	}
	handler := &Handler{
		messageService:               messageService,
		maintenanceTerminalFinalizer: finalizer,
	}
	message := terminalCallsiteAssistant()

	eventBus := event.NewEventBus()
	cancelled := false
	cancel := func() {
		cancelled = true
	}

	handler.setupStopEventHandler(
		eventBus,
		message.SessionID,
		12,
		message,
		cancel,
	)

	if err := eventBus.Emit(
		terminalCallsiteActorContext(),
		event.Event{
			Type:      event.EventStop,
			SessionID: message.SessionID,
		},
	); err != nil {
		t.Fatalf("stop event emit error = %v", err)
	}

	if !cancelled {
		t.Fatal("stop handler did not cancel generation")
	}
	if finalizer.calls != 1 {
		t.Fatalf("terminal finalizer calls = %d, want 1", finalizer.calls)
	}
	if finalizer.reason != maintenanceprojection.TerminalReasonStop {
		t.Fatalf(
			"terminal reason = %q, want %q",
			finalizer.reason,
			maintenanceprojection.TerminalReasonStop,
		)
	}
	if finalizer.msg != message {
		t.Fatal("stop terminal finalizer did not receive exact assistant message")
	}
	if !reflect.DeepEqual(finalizer.actor, maintenanceproxy.Actor{}) {
		t.Fatalf(
			"stop terminal actor = %#v, want empty actor",
			finalizer.actor,
		)
	}

	updateCalls, _ := messageService.counts()
	if updateCalls != 0 {
		t.Fatalf(
			"legacy UpdateMessage calls = %d, want 0",
			updateCalls,
		)
	}
}
