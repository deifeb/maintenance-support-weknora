package messagefinalizationcontract_test

import (
	"context"
	"errors"
	"fmt"
	"strings"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	"github.com/Tencent/WeKnora/internal/application/repository"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/require"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func terminalUpdateMatcher(_ string, actual string) error {
	normalized := strings.ToLower(
		strings.Join(strings.Fields(actual), " "),
	)
	parts := strings.SplitN(normalized, " where ", 2)
	if len(parts) != 2 {
		return fmt.Errorf("terminal update must contain WHERE: %s", actual)
	}
	setClause := parts[0]
	whereClause := parts[1]

	for _, required := range []string{
		`update "messages" set`,
		`"content"=`,
		`"knowledge_references"=`,
		`"agent_steps"=`,
		`"is_completed"=`,
		`"is_fallback"=`,
		`"agent_duration_ms"=`,
		`"maintenance_cards"=`,
		`"execution_context"=`,
		`"updated_at"=`,
	} {
		if !strings.Contains(setClause, required) {
			return fmt.Errorf(
				"terminal update SET missing %q: %s",
				required,
				actual,
			)
		}
	}

	for _, forbidden := range []string{
		`"id"=`,
		`"session_id"=`,
		`"role"=`,
		`"request_id"=`,
		`"created_at"=`,
		`"deleted_at"=`,
	} {
		if strings.Contains(setClause, forbidden) {
			return fmt.Errorf(
				"terminal update must not rewrite %q: %s",
				forbidden,
				actual,
			)
		}
	}

	for _, required := range []string{
		"id =",
		"session_id =",
		"role =",
		"is_completed =",
	} {
		if !strings.Contains(whereClause, required) {
			return fmt.Errorf(
				"terminal update WHERE missing %q: %s",
				required,
				actual,
			)
		}
	}

	return nil
}

func openRepository(t *testing.T) (
	*gorm.DB,
	sqlmock.Sqlmock,
	func(),
) {
	t.Helper()

	sqlDB, mock, err := sqlmock.New(
		sqlmock.QueryMatcherOption(
			sqlmock.QueryMatcherFunc(terminalUpdateMatcher),
		),
	)
	require.NoError(t, err)

	gormDB, err := gorm.Open(
		postgres.New(postgres.Config{
			Conn:                 sqlDB,
			PreferSimpleProtocol: true,
		}),
		&gorm.Config{
			SkipDefaultTransaction: true,
		},
	)
	require.NoError(t, err)

	return gormDB, mock, func() {
		mock.ExpectClose()
		require.NoError(t, sqlDB.Close())
		require.NoError(t, mock.ExpectationsWereMet())
	}
}

func terminalRepositoryMessage() *types.Message {
	return &types.Message{
		ID:                  "assistant-1",
		SessionID:           "session-1",
		RequestID:           "req-1",
		Role:                "assistant",
		Content:             "final assistant text",
		IsCompleted:         true,
		IsFallback:          true,
		AgentDurationMs:     1234,
		KnowledgeReferences: types.References{},
		AgentSteps:          types.AgentSteps{},
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
		ExecutionContext: types.MessageExecutionContext{
			Locale: "en",
			MaintenanceProjection: &types.MaintenanceProjectionProvenance{
				SchemaVersion:    "1.0",
				SourceKind:       "AI_MESSAGE_TRIGGER",
				AISessionID:      123,
				TriggerMessageID: 456,
			},
		},
		UpdatedAt: time.Date(
			2026, 8, 30, 3, 30, 0, 0, time.UTC,
		),
	}
}

func TestFinalizeAssistantMessageIfOpenAtomicallyPersistsTerminalSnapshot(
	t *testing.T,
) {
	gormDB, mock, closeDB := openRepository(t)
	defer closeDB()

	mock.ExpectExec("terminal finalize").
		WillReturnResult(sqlmock.NewResult(0, 1))

	repo := repository.NewMessageRepository(gormDB)

	persisted, err := repo.FinalizeAssistantMessageIfOpen(
		context.Background(),
		terminalRepositoryMessage(),
	)
	require.NoError(t, err)
	require.True(t, persisted)
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestFinalizeAssistantMessageIfOpenReportsAlreadyFinalizedWithoutOverwrite(
	t *testing.T,
) {
	gormDB, mock, closeDB := openRepository(t)
	defer closeDB()

	mock.ExpectExec("terminal finalize").
		WillReturnResult(sqlmock.NewResult(0, 0))

	repo := repository.NewMessageRepository(gormDB)

	persisted, err := repo.FinalizeAssistantMessageIfOpen(
		context.Background(),
		terminalRepositoryMessage(),
	)
	require.NoError(t, err)
	require.False(t, persisted)
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestFinalizeAssistantMessageIfOpenPropagatesDatabaseFailure(
	t *testing.T,
) {
	gormDB, mock, closeDB := openRepository(t)
	defer closeDB()

	databaseErr := errors.New("database unavailable")
	mock.ExpectExec("terminal finalize").
		WillReturnError(databaseErr)

	repo := repository.NewMessageRepository(gormDB)

	persisted, err := repo.FinalizeAssistantMessageIfOpen(
		context.Background(),
		terminalRepositoryMessage(),
	)
	require.False(t, persisted)
	require.ErrorIs(t, err, databaseErr)
	require.NoError(t, mock.ExpectationsWereMet())
}
