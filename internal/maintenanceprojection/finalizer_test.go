package maintenanceprojection

import (
	"context"
	"errors"
	"sync"
	"testing"
	"time"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/require"
)

type fakeTerminalProjectionClient struct {
	mu      sync.Mutex
	calls   int
	cards   types.MaintenanceCards
	err     error
	started chan struct{}
	release chan struct{}
}

func (f *fakeTerminalProjectionClient) RecoverExactTurn(
	ctx context.Context,
	actor maintenanceproxy.Actor,
	source types.MaintenanceProjectionProvenance,
) (types.MaintenanceCards, error) {
	f.mu.Lock()
	f.calls++
	started := f.started
	release := f.release
	cards := append(types.MaintenanceCards(nil), f.cards...)
	err := f.err
	f.mu.Unlock()

	if started != nil {
		select {
		case started <- struct{}{}:
		default:
		}
	}
	if release != nil {
		select {
		case <-release:
		case <-ctx.Done():
			return nil, ctx.Err()
		}
	}
	return cards, err
}

func (f *fakeTerminalProjectionClient) callCount() int {
	f.mu.Lock()
	defer f.mu.Unlock()
	return f.calls
}

type fakeTerminalMessageStore struct {
	mu          sync.Mutex
	finalized   map[string]bool
	calls       int
	failNext    error
	lastMessage *types.Message
}

func newFakeTerminalMessageStore() *fakeTerminalMessageStore {
	return &fakeTerminalMessageStore{
		finalized: make(map[string]bool),
	}
}

func terminalMessageKey(message *types.Message) string {
	return message.SessionID + "/" + message.ID
}

func cloneTerminalMessage(message *types.Message) *types.Message {
	if message == nil {
		return nil
	}
	cloned := *message
	cloned.MaintenanceCards = append(
		types.MaintenanceCards(nil),
		message.MaintenanceCards...,
	)
	return &cloned
}

func (s *fakeTerminalMessageStore) FinalizeAssistantMessageIfOpen(
	ctx context.Context,
	message *types.Message,
) (bool, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	s.calls++
	if s.failNext != nil {
		err := s.failNext
		s.failNext = nil
		return false, err
	}

	key := terminalMessageKey(message)
	if s.finalized[key] {
		return false, nil
	}
	s.finalized[key] = true
	s.lastMessage = cloneTerminalMessage(message)
	return true, nil
}

func (s *fakeTerminalMessageStore) snapshot() (*types.Message, int) {
	s.mu.Lock()
	defer s.mu.Unlock()
	return cloneTerminalMessage(s.lastMessage), s.calls
}

func terminalActor() maintenanceproxy.Actor {
	return maintenanceproxy.Actor{
		UserID:    "user-7",
		TenantID:  "42",
		Roles:     []string{"viewer"},
		RequestID: "req-terminal",
	}
}

func terminalProvenance() *types.MaintenanceProjectionProvenance {
	return &types.MaintenanceProjectionProvenance{
		SchemaVersion:    "1.0",
		SourceKind:       "AI_MESSAGE_TRIGGER",
		AISessionID:      123,
		TriggerMessageID: 456,
	}
}

func terminalCard() types.MaintenanceCard {
	return types.MaintenanceCard{
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
	}
}

func openAssistantMessage() *types.Message {
	return &types.Message{
		ID:          "assistant-1",
		SessionID:   "session-1",
		Role:        "assistant",
		Content:     "normal assistant text",
		IsCompleted: false,
		ExecutionContext: types.MessageExecutionContext{
			Locale:                "en",
			MaintenanceProjection: terminalProvenance(),
		},
	}
}

func TestTerminalFinalizerNormalCompletionPersistsProjectionOnSameAssistantOnce(
	t *testing.T,
) {
	client := &fakeTerminalProjectionClient{
		cards: types.MaintenanceCards{terminalCard()},
	}
	store := newFakeTerminalMessageStore()
	finalizer := NewTerminalFinalizer(client, store)

	message := openAssistantMessage()
	result, err := finalizer.Finalize(
		context.Background(),
		terminalActor(),
		message,
		TerminalReasonNormal,
	)
	require.NoError(t, err)
	require.True(t, result.Persisted)
	require.NoError(t, result.ProjectionError)

	persisted, calls := store.snapshot()
	require.Equal(t, 1, calls)
	require.NotNil(t, persisted)
	require.Equal(t, "session-1", persisted.SessionID)
	require.Equal(t, "assistant-1", persisted.ID)
	require.True(t, persisted.IsCompleted)
	require.Equal(t, "normal assistant text", persisted.Content)
	require.Len(t, persisted.MaintenanceCards, 1)
	require.Equal(t, "CALCULATION", persisted.MaintenanceCards[0].Type)
	require.NotNil(t, persisted.ExecutionContext.MaintenanceProjection)
	require.EqualValues(
		t,
		456,
		persisted.ExecutionContext.MaintenanceProjection.TriggerMessageID,
	)
	require.Equal(t, 1, client.callCount())

	// Once the same in-memory message is durably finalized, a duplicate
	// completion callback is a no-op: no second projection and no second write.
	result, err = finalizer.Finalize(
		context.Background(),
		terminalActor(),
		message,
		TerminalReasonNormal,
	)
	require.NoError(t, err)
	require.False(t, result.Persisted)
	require.Equal(t, 1, client.callCount())

	_, calls = store.snapshot()
	require.Equal(t, 1, calls)
}

func TestTerminalFinalizerProjectionFailureFailsClosedButCompletesText(
	t *testing.T,
) {
	projectionErr := errors.New("upstream invalid response")
	client := &fakeTerminalProjectionClient{err: projectionErr}
	store := newFakeTerminalMessageStore()
	finalizer := NewTerminalFinalizer(client, store)

	message := openAssistantMessage()
	result, err := finalizer.Finalize(
		context.Background(),
		terminalActor(),
		message,
		TerminalReasonNormal,
	)
	require.NoError(t, err)
	require.True(t, result.Persisted)
	require.ErrorIs(t, result.ProjectionError, projectionErr)

	persisted, calls := store.snapshot()
	require.Equal(t, 1, calls)
	require.True(t, persisted.IsCompleted)
	require.Equal(t, "normal assistant text", persisted.Content)
	require.Empty(t, persisted.MaintenanceCards)
	require.NotNil(t, persisted.ExecutionContext.MaintenanceProjection)
}

func TestTerminalFinalizerPersistenceFailureLeavesMessageOpenForExactRetry(
	t *testing.T,
) {
	client := &fakeTerminalProjectionClient{
		cards: types.MaintenanceCards{terminalCard()},
	}
	store := newFakeTerminalMessageStore()
	store.failNext = errors.New("database unavailable")
	finalizer := NewTerminalFinalizer(client, store)

	message := openAssistantMessage()

	first, err := finalizer.Finalize(
		context.Background(),
		terminalActor(),
		message,
		TerminalReasonNormal,
	)
	require.Error(t, err)
	require.False(t, first.Persisted)
	require.False(t, message.IsCompleted)
	require.Empty(t, message.MaintenanceCards)

	second, err := finalizer.Finalize(
		context.Background(),
		terminalActor(),
		message,
		TerminalReasonNormal,
	)
	require.NoError(t, err)
	require.True(t, second.Persisted)
	require.True(t, message.IsCompleted)
	require.Len(t, message.MaintenanceCards, 1)
	require.Equal(t, 2, client.callCount())

	persisted, calls := store.snapshot()
	require.Equal(t, 2, calls)
	require.Len(t, persisted.MaintenanceCards, 1)
	require.Equal(t, terminalCard(), persisted.MaintenanceCards[0])
}

func TestTerminalFinalizerStopDoesNotRequestProjection(t *testing.T) {
	client := &fakeTerminalProjectionClient{
		cards: types.MaintenanceCards{terminalCard()},
	}
	store := newFakeTerminalMessageStore()
	finalizer := NewTerminalFinalizer(client, store)

	message := openAssistantMessage()
	result, err := finalizer.Finalize(
		context.Background(),
		terminalActor(),
		message,
		TerminalReasonStop,
	)
	require.NoError(t, err)
	require.True(t, result.Persisted)
	require.Equal(t, 0, client.callCount())

	persisted, calls := store.snapshot()
	require.Equal(t, 1, calls)
	require.True(t, persisted.IsCompleted)
	require.Empty(t, persisted.MaintenanceCards)
}

func TestTerminalFinalizerStopWinBlocksLateProjectionWrite(t *testing.T) {
	started := make(chan struct{}, 1)
	release := make(chan struct{})
	client := &fakeTerminalProjectionClient{
		cards:   types.MaintenanceCards{terminalCard()},
		started: started,
		release: release,
	}
	store := newFakeTerminalMessageStore()
	finalizer := NewTerminalFinalizer(client, store)

	// Two handler callbacks may hold separate snapshots of the same still-open
	// database row. The store is the final race arbiter.
	normalSnapshot := openAssistantMessage()
	stopSnapshot := openAssistantMessage()

	type finalizeResponse struct {
		result TerminalFinalizeResult
		err    error
	}
	normalDone := make(chan finalizeResponse, 1)
	go func() {
		result, err := finalizer.Finalize(
			context.Background(),
			terminalActor(),
			normalSnapshot,
			TerminalReasonNormal,
		)
		normalDone <- finalizeResponse{result: result, err: err}
	}()

	select {
	case <-started:
	case <-time.After(time.Second):
		t.Fatal("normal projection did not start")
	}

	stopResult, err := finalizer.Finalize(
		context.Background(),
		terminalActor(),
		stopSnapshot,
		TerminalReasonStop,
	)
	require.NoError(t, err)
	require.True(t, stopResult.Persisted)

	close(release)

	select {
	case response := <-normalDone:
		require.NoError(t, response.err)
		require.False(t, response.result.Persisted)
	case <-time.After(time.Second):
		t.Fatal("normal finalization did not finish")
	}

	persisted, calls := store.snapshot()
	require.Equal(t, 2, calls)
	require.NotNil(t, persisted)
	require.True(t, persisted.IsCompleted)
	require.Empty(
		t,
		persisted.MaintenanceCards,
		"late normal projection must not overwrite stop-finalized row",
	)
	require.Equal(t, 1, client.callCount())
}
