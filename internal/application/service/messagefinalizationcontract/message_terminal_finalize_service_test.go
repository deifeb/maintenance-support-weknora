package messagefinalizationcontract_test

import (
	"context"
	"errors"
	"testing"

	"github.com/Tencent/WeKnora/internal/application/service"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
	"github.com/stretchr/testify/require"
)

type fakeTerminalMessageRepository struct {
	interfaces.MessageRepository

	calls   int
	message *types.Message
	result  bool
	err     error
}

func (f *fakeTerminalMessageRepository) FinalizeAssistantMessageIfOpen(
	ctx context.Context,
	message *types.Message,
) (bool, error) {
	f.calls++
	f.message = message
	return f.result, f.err
}

type fakeTerminalSessionRepository struct {
	interfaces.SessionRepository

	calls     int
	tenantID  uint64
	userID    string
	sessionID string
	err       error
}

func (f *fakeTerminalSessionRepository) Get(
	ctx context.Context,
	tenantID uint64,
	userID string,
	sessionID string,
) (*types.Session, error) {
	f.calls++
	f.tenantID = tenantID
	f.userID = userID
	f.sessionID = sessionID
	if f.err != nil {
		return nil, f.err
	}
	return &types.Session{
		ID:       sessionID,
		TenantID: tenantID,
	}, nil
}

func terminalServiceContext() context.Context {
	return context.WithValue(
		context.Background(),
		types.TenantIDContextKey,
		uint64(42),
	)
}

func terminalServiceMessage() *types.Message {
	return &types.Message{
		ID:          "assistant-1",
		SessionID:   "session-1",
		Role:        "assistant",
		Content:     "final assistant text",
		IsCompleted: true,
		MaintenanceCards: types.MaintenanceCards{
			{
				SchemaVersion: "1.0",
				Type:          "CALCULATION",
				Title:         "Calculation created",
				Summary:       "Open calculation progress.",
				Status:        "PENDING",
				Target: types.MaintenanceCardTarget{
					ObjectType:      "CALCULATION_GROUP",
					ObjectID:        35,
					ObservedVersion: 1,
					NavigationPath:  "/platform/maintenance/calculations/35/progress",
				},
				ObservedAt: "2026-08-29T00:00:00Z",
				Payload: map[string]any{
					"group_id":                35,
					"scenario_version_id":     7,
					"status":                  "PENDING",
					"primary_candidate_key":   "base",
					"current_candidate_count": 2,
					"observed_version":        1,
				},
			},
		},
	}
}

func newTerminalMessageService(
	messageRepo interfaces.MessageRepository,
	sessionRepo interfaces.SessionRepository,
) interfaces.MessageService {
	return service.NewMessageService(
		messageRepo,
		sessionRepo,
		nil,
		nil,
		nil,
		nil,
		nil,
	)
}

func TestMessageServiceFinalizesExactAssistantThroughConditionalRepositoryWrite(
	t *testing.T,
) {
	messageRepo := &fakeTerminalMessageRepository{
		result: true,
	}
	sessionRepo := &fakeTerminalSessionRepository{}
	messageService := newTerminalMessageService(
		messageRepo,
		sessionRepo,
	)

	message := terminalServiceMessage()
	persisted, err := messageService.FinalizeAssistantMessageIfOpen(
		terminalServiceContext(),
		message,
	)
	require.NoError(t, err)
	require.True(t, persisted)

	require.Equal(t, 1, sessionRepo.calls)
	require.EqualValues(t, 42, sessionRepo.tenantID)
	require.Equal(t, "session-1", sessionRepo.sessionID)

	require.Equal(t, 1, messageRepo.calls)
	require.Same(t, message, messageRepo.message)
}

func TestMessageServicePreservesAlreadyFinalizedResult(t *testing.T) {
	messageRepo := &fakeTerminalMessageRepository{
		result: false,
	}
	sessionRepo := &fakeTerminalSessionRepository{}
	messageService := newTerminalMessageService(
		messageRepo,
		sessionRepo,
	)

	persisted, err := messageService.FinalizeAssistantMessageIfOpen(
		terminalServiceContext(),
		terminalServiceMessage(),
	)
	require.NoError(t, err)
	require.False(t, persisted)
	require.Equal(t, 1, messageRepo.calls)
}

func TestMessageServiceRejectsTerminalWriteWhenSessionScopeFails(
	t *testing.T,
) {
	scopeErr := errors.New("session not visible")
	messageRepo := &fakeTerminalMessageRepository{
		result: true,
	}
	sessionRepo := &fakeTerminalSessionRepository{
		err: scopeErr,
	}
	messageService := newTerminalMessageService(
		messageRepo,
		sessionRepo,
	)

	persisted, err := messageService.FinalizeAssistantMessageIfOpen(
		terminalServiceContext(),
		terminalServiceMessage(),
	)
	require.False(t, persisted)
	require.ErrorIs(t, err, scopeErr)
	require.Equal(t, 1, sessionRepo.calls)
	require.Equal(t, 0, messageRepo.calls)
}

func TestMessageServicePropagatesTerminalRepositoryFailure(
	t *testing.T,
) {
	repositoryErr := errors.New("terminal update failed")
	messageRepo := &fakeTerminalMessageRepository{
		err: repositoryErr,
	}
	sessionRepo := &fakeTerminalSessionRepository{}
	messageService := newTerminalMessageService(
		messageRepo,
		sessionRepo,
	)

	persisted, err := messageService.FinalizeAssistantMessageIfOpen(
		terminalServiceContext(),
		terminalServiceMessage(),
	)
	require.False(t, persisted)
	require.ErrorIs(t, err, repositoryErr)
	require.Equal(t, 1, messageRepo.calls)
}
