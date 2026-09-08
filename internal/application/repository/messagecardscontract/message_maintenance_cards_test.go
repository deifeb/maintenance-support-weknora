package messagecardscontract_test

import (
	"context"
	"database/sql/driver"
	"encoding/json"
	"regexp"
	"testing"
	"time"

	"github.com/DATA-DOG/go-sqlmock"
	repository "github.com/Tencent/WeKnora/internal/application/repository"
	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/require"
	"gorm.io/driver/postgres"
	"gorm.io/gorm"
)

func newMockRepository(t *testing.T) (
	typesMessageRepository,
	sqlmock.Sqlmock,
) {
	t.Helper()

	sqlDB, mock, err := sqlmock.New()
	require.NoError(t, err)
	t.Cleanup(func() {
		_ = sqlDB.Close()
	})

	db, err := gorm.Open(
		postgres.New(postgres.Config{
			Conn:                 sqlDB,
			PreferSimpleProtocol: true,
		}),
		&gorm.Config{
			SkipDefaultTransaction: true,
		},
	)
	require.NoError(t, err)

	return typesMessageRepository{
		repo: repository.NewMessageRepository(db),
	}, mock
}

type typesMessageRepository struct {
	repo interface {
		GetMessagesBySession(
			context.Context,
			string,
			int,
			int,
		) ([]*types.Message, error)
		UpdateMessageMaintenanceCards(
			context.Context,
			string,
			string,
			types.MaintenanceCards,
		) error
	}
}

func sampleCard() types.MaintenanceCard {
	return types.MaintenanceCard{
		SchemaVersion: "1.0",
		Type:          "CALCULATION",
		Title:         "Calculation created",
		Summary:       "Open the progress page.",
		Status:        "PENDING",
		Target: types.MaintenanceCardTarget{
			ObjectType:      "CALCULATION_GROUP",
			ObjectID:        35,
			ObservedVersion: 1,
			NavigationPath: "/platform/maintenance/" +
				"calculations/35/progress",
		},
		ObservedAt: "2026-08-29T00:00:00Z",
		Payload: map[string]any{
			"group_id": 35,
		},
	}
}

func driverJSON(t *testing.T, value driver.Value) string {
	t.Helper()

	switch typed := value.(type) {
	case []byte:
		return string(typed)
	case string:
		return typed
	default:
		t.Fatalf("unexpected driver.Value type %T", value)
		return ""
	}
}

func TestMaintenanceCardsValueAndScanRoundTrip(t *testing.T) {
	cards := types.MaintenanceCards{sampleCard()}

	value, err := cards.Value()
	require.NoError(t, err)

	var scanned types.MaintenanceCards
	require.NoError(t, scanned.Scan(value))

	expected, err := json.Marshal(cards)
	require.NoError(t, err)
	actual, err := json.Marshal(scanned)
	require.NoError(t, err)

	require.JSONEq(t, string(expected), string(actual))
}

func TestMaintenanceCardsNilStorageNormalizesToEmpty(t *testing.T) {
	var cards types.MaintenanceCards

	value, err := cards.Value()
	require.NoError(t, err)
	require.JSONEq(t, "[]", driverJSON(t, value))

	require.NoError(t, cards.Scan(nil))
	require.NotNil(t, cards)
	require.Empty(t, cards)

	require.NoError(t, cards.Scan([]byte("null")))
	require.NotNil(t, cards)
	require.Empty(t, cards)
}

func TestNewMessageDefaultsMaintenanceCardsToEmpty(t *testing.T) {
	message := &types.Message{}

	require.NoError(t, message.BeforeCreate(nil))
	require.NotNil(t, message.MaintenanceCards)
	require.Empty(t, message.MaintenanceCards)
}

func TestEmptyMaintenanceCardsDoNotChangeOrdinaryMessageJSON(
	t *testing.T,
) {
	message := types.Message{
		ID:               "message-1",
		SessionID:        "session-1",
		Content:          "answer",
		Role:             "assistant",
		MaintenanceCards: types.MaintenanceCards{},
	}

	payload, err := json.Marshal(message)
	require.NoError(t, err)
	require.NotContains(
		t,
		string(payload),
		`"maintenance_cards"`,
	)
}

func TestUpdateMessageMaintenanceCardsOnlyTouchesCardColumn(
	t *testing.T,
) {
	wrapped, mock := newMockRepository(t)
	cards := types.MaintenanceCards{sampleCard()}

	updateSQL := regexp.QuoteMeta(
		`UPDATE "messages" SET "maintenance_cards"=$1,` +
			`"updated_at"=$2 WHERE (id = $3 AND session_id = $4) ` +
			`AND "messages"."deleted_at" IS NULL`,
	)
	mock.ExpectExec(updateSQL).
		WithArgs(
			sqlmock.AnyArg(),
			sqlmock.AnyArg(),
			"message-1",
			"session-1",
		).
		WillReturnResult(sqlmock.NewResult(0, 1))

	err := wrapped.repo.UpdateMessageMaintenanceCards(
		context.Background(),
		"session-1",
		"message-1",
		cards,
	)
	require.NoError(t, err)
	require.NoError(t, mock.ExpectationsWereMet())
}

func TestHistoryLoadReturnsExactMaintenanceCardSnapshot(
	t *testing.T,
) {
	wrapped, mock := newMockRepository(t)
	cardJSON, err := json.Marshal(
		types.MaintenanceCards{sampleCard()},
	)
	require.NoError(t, err)

	now := time.Date(
		2026,
		8,
		29,
		0,
		0,
		0,
		0,
		time.UTC,
	)

	query := `SELECT .* FROM "messages" ` +
		`WHERE session_id = \$1 .*` +
		`ORDER BY created_at ASC LIMIT \$2`
	rows := sqlmock.NewRows([]string{
		"id",
		"session_id",
		"request_id",
		"content",
		"role",
		"maintenance_cards",
		"created_at",
		"updated_at",
	}).
		AddRow(
			"message-1",
			"session-1",
			"request-1",
			"answer",
			"assistant",
			cardJSON,
			now,
			now,
		)

	mock.ExpectQuery(query).
		WithArgs("session-1", 20).
		WillReturnRows(rows)

	messages, err := wrapped.repo.GetMessagesBySession(
		context.Background(),
		"session-1",
		1,
		20,
	)
	require.NoError(t, err)
	require.Len(t, messages, 1)
	require.Len(t, messages[0].MaintenanceCards, 1)

	actualCards, err := json.Marshal(
		messages[0].MaintenanceCards,
	)
	require.NoError(t, err)
	require.JSONEq(t, string(cardJSON), string(actualCards))

	historyJSON, err := json.Marshal(messages[0])
	require.NoError(t, err)
	require.Contains(
		t,
		string(historyJSON),
		`"maintenance_cards"`,
	)

	require.NoError(t, mock.ExpectationsWereMet())
}
