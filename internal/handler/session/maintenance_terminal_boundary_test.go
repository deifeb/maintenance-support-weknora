package session

import (
	"context"
	"errors"
	"reflect"
	"testing"

	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
)

type recordingMaintenanceTerminalFinalizer struct {
	calls   int
	ctx     context.Context
	actor   maintenanceproxy.Actor
	message *types.Message
	reason  maintenanceprojection.TerminalReason
	result  maintenanceprojection.TerminalFinalizeResult
	err     error
}

func (f *recordingMaintenanceTerminalFinalizer) Finalize(
	ctx context.Context,
	actor maintenanceproxy.Actor,
	message *types.Message,
	reason maintenanceprojection.TerminalReason,
) (maintenanceprojection.TerminalFinalizeResult, error) {
	f.calls++
	f.ctx = ctx
	f.actor = actor
	f.message = message
	f.reason = reason
	return f.result, f.err
}

func terminalBoundaryContext() context.Context {
	ctx := context.Background()
	ctx = context.WithValue(
		ctx,
		types.RequestIDContextKey,
		"req-terminal-handler",
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

func maintenanceBackedAssistant() *types.Message {
	return &types.Message{
		ID:        "assistant-1",
		SessionID: "session-1",
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

func ordinaryAssistant() *types.Message {
	return &types.Message{
		ID:        "assistant-ordinary",
		SessionID: "session-ordinary",
		Role:      "assistant",
		Content:   "ordinary chat text",
	}
}

func newHandlerWithMaintenanceTerminalFinalizer(
	finalizer *recordingMaintenanceTerminalFinalizer,
) *Handler {
	return &Handler{
		maintenanceTerminalFinalizer: finalizer,
	}
}

func TestFinalizeAssistantTerminalNormalUsesExactAsyncMaintenanceActor(
	t *testing.T,
) {
	finalizer := &recordingMaintenanceTerminalFinalizer{}
	handler := newHandlerWithMaintenanceTerminalFinalizer(finalizer)
	message := maintenanceBackedAssistant()
	ctx := terminalBoundaryContext()

	result, err := handler.finalizeAssistantTerminal(
		ctx,
		message,
		maintenanceprojection.TerminalReasonNormal,
	)
	if err != nil {
		t.Fatalf("finalizeAssistantTerminal() error = %v", err)
	}
	if result != finalizer.result {
		t.Fatalf(
			"result = %#v, want %#v",
			result,
			finalizer.result,
		)
	}

	if finalizer.calls != 1 {
		t.Fatalf("finalizer calls = %d, want 1", finalizer.calls)
	}
	if finalizer.ctx != ctx {
		t.Fatal("finalizer did not receive the exact terminal context")
	}
	if finalizer.message != message {
		t.Fatal("finalizer did not receive the exact assistant message")
	}
	if finalizer.reason != maintenanceprojection.TerminalReasonNormal {
		t.Fatalf(
			"reason = %q, want %q",
			finalizer.reason,
			maintenanceprojection.TerminalReasonNormal,
		)
	}

	expectedActor := maintenanceproxy.Actor{
		UserID:    "user-1",
		TenantID:  "12",
		Roles:     []string{"contributor"},
		RequestID: "req-terminal-handler",
	}
	if !reflect.DeepEqual(finalizer.actor, expectedActor) {
		t.Fatalf(
			"actor = %#v, want %#v",
			finalizer.actor,
			expectedActor,
		)
	}
}

func TestFinalizeAssistantTerminalOrdinaryNormalDoesNotRequireMaintenanceActor(
	t *testing.T,
) {
	finalizer := &recordingMaintenanceTerminalFinalizer{}
	handler := newHandlerWithMaintenanceTerminalFinalizer(finalizer)
	message := ordinaryAssistant()

	result, err := handler.finalizeAssistantTerminal(
		context.Background(),
		message,
		maintenanceprojection.TerminalReasonNormal,
	)
	if err != nil {
		t.Fatalf("finalizeAssistantTerminal() error = %v", err)
	}
	if result != finalizer.result {
		t.Fatalf(
			"result = %#v, want %#v",
			result,
			finalizer.result,
		)
	}
	if finalizer.calls != 1 {
		t.Fatalf("finalizer calls = %d, want 1", finalizer.calls)
	}
	if !reflect.DeepEqual(finalizer.actor, maintenanceproxy.Actor{}) {
		t.Fatalf(
			"ordinary-chat actor = %#v, want empty actor",
			finalizer.actor,
		)
	}
}

func TestFinalizeAssistantTerminalStopNeverRequiresProjectionActor(
	t *testing.T,
) {
	finalizer := &recordingMaintenanceTerminalFinalizer{}
	handler := newHandlerWithMaintenanceTerminalFinalizer(finalizer)
	message := maintenanceBackedAssistant()

	result, err := handler.finalizeAssistantTerminal(
		context.Background(),
		message,
		maintenanceprojection.TerminalReasonStop,
	)
	if err != nil {
		t.Fatalf("finalizeAssistantTerminal() error = %v", err)
	}
	if result != finalizer.result {
		t.Fatalf(
			"result = %#v, want %#v",
			result,
			finalizer.result,
		)
	}
	if finalizer.calls != 1 {
		t.Fatalf("finalizer calls = %d, want 1", finalizer.calls)
	}
	if finalizer.reason != maintenanceprojection.TerminalReasonStop {
		t.Fatalf(
			"reason = %q, want %q",
			finalizer.reason,
			maintenanceprojection.TerminalReasonStop,
		)
	}
	if !reflect.DeepEqual(finalizer.actor, maintenanceproxy.Actor{}) {
		t.Fatalf(
			"stop actor = %#v, want empty actor",
			finalizer.actor,
		)
	}
}

func TestFinalizeAssistantTerminalInvalidMaintenanceActorStillFinalizesFailClosed(
	t *testing.T,
) {
	finalizer := &recordingMaintenanceTerminalFinalizer{
		result: maintenanceprojection.TerminalFinalizeResult{
			Persisted:       true,
			ProjectionError: errors.New("projection unavailable"),
		},
	}
	handler := newHandlerWithMaintenanceTerminalFinalizer(finalizer)
	message := maintenanceBackedAssistant()

	ctx := terminalBoundaryContext()
	ctx = context.WithValue(
		ctx,
		types.PrincipalContextKey,
		types.Principal{
			Type: types.PrincipalWebUser,
			ID:   "other-user",
		},
	)

	result, err := handler.finalizeAssistantTerminal(
		ctx,
		message,
		maintenanceprojection.TerminalReasonNormal,
	)
	if err != nil {
		t.Fatalf(
			"actor resolution must not block terminal persistence: %v",
			err,
		)
	}
	if !result.Persisted {
		t.Fatal("terminal result Persisted = false, want true")
	}
	if result.ProjectionError == nil {
		t.Fatal("terminal ProjectionError = nil, want fail-closed projection error")
	}
	if finalizer.calls != 1 {
		t.Fatalf("finalizer calls = %d, want 1", finalizer.calls)
	}
	if !reflect.DeepEqual(finalizer.actor, maintenanceproxy.Actor{}) {
		t.Fatalf(
			"invalid-identity actor = %#v, want empty actor",
			finalizer.actor,
		)
	}
}

func TestFinalizeAssistantTerminalPropagatesDurablePersistenceFailure(
	t *testing.T,
) {
	persistenceErr := errors.New("conditional terminal update failed")
	finalizer := &recordingMaintenanceTerminalFinalizer{
		err: persistenceErr,
	}
	handler := newHandlerWithMaintenanceTerminalFinalizer(finalizer)

	result, err := handler.finalizeAssistantTerminal(
		context.Background(),
		ordinaryAssistant(),
		maintenanceprojection.TerminalReasonNormal,
	)
	if !errors.Is(err, persistenceErr) {
		t.Fatalf(
			"error = %v, want %v",
			err,
			persistenceErr,
		)
	}
	if result.Persisted {
		t.Fatal("Persisted = true on persistence failure")
	}
}
