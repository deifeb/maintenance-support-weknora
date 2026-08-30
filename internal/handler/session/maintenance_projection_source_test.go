package session

import (
	"context"
	"net/http"
	"net/http/httptest"
	"strings"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/Tencent/WeKnora/internal/types/interfaces"
	"github.com/gin-gonic/gin"
	"github.com/stretchr/testify/require"
)

type maintenanceProjectionSourceSessionService struct {
	interfaces.SessionService
	session *types.Session
}

func (s *maintenanceProjectionSourceSessionService) GetOwnedSession(
	ctx context.Context,
	id string,
) (*types.Session, error) {
	return s.session, nil
}

func newMaintenanceProjectionParseHandler() *Handler {
	return &Handler{
		sessionService: &maintenanceProjectionSourceSessionService{
			session: &types.Session{
				ID:       "session-maintenance-source",
				TenantID: 12,
			},
		},
	}
}

func newMaintenanceProjectionParseContext(
	t *testing.T,
	body string,
) *gin.Context {
	t.Helper()

	gin.SetMode(gin.TestMode)
	recorder := httptest.NewRecorder()
	ctx, _ := gin.CreateTestContext(recorder)
	request := httptest.NewRequest(
		http.MethodPost,
		"/api/v1/sessions/session-maintenance-source/knowledge-qa",
		strings.NewReader(body),
	)
	request.Header.Set("Content-Type", "application/json")
	ctx.Request = request
	ctx.Params = gin.Params{
		{
			Key:   "session_id",
			Value: "session-maintenance-source",
		},
	}
	ctx.Set(types.RequestIDContextKey.String(), "request-maintenance-source")
	ctx.Set(types.TenantIDContextKey.String(), uint64(12))
	ctx.Set(types.UserIDContextKey.String(), "user-maintenance-source")
	return ctx
}

func TestParseQARequestCopiesExactMaintenanceProjectionSourceToSameAssistant(
	t *testing.T,
) {
	handler := newMaintenanceProjectionParseHandler()
	ctx := newMaintenanceProjectionParseContext(
		t,
		`{
			"query":"continue with this maintenance result",
			"maintenance_projection_source":{
				"schema_version":"1.0",
				"source_kind":"AI_MESSAGE_TRIGGER",
				"ai_session_id":123,
				"trigger_message_id":456
			}
		}`,
	)

	reqCtx, _, err := handler.parseQARequest(
		ctx,
		"maintenance-source-test",
	)
	require.NoError(t, err)
	require.NotNil(t, reqCtx)
	require.NotNil(t, reqCtx.assistantMessage)

	source := reqCtx.assistantMessage.ExecutionContext.MaintenanceProjection
	require.NotNil(
		t,
		source,
		"exact Maintenance source must be copied onto the same assistant message",
	)
	require.Equal(t, "1.0", source.SchemaVersion)
	require.Equal(t, "AI_MESSAGE_TRIGGER", source.SourceKind)
	require.EqualValues(t, 123, source.AISessionID)
	require.EqualValues(t, 456, source.TriggerMessageID)
}

func TestParseQARequestOrdinaryChatLeavesMaintenanceProjectionSourceEmpty(
	t *testing.T,
) {
	handler := newMaintenanceProjectionParseHandler()
	ctx := newMaintenanceProjectionParseContext(
		t,
		`{"query":"ordinary chat without maintenance source"}`,
	)

	reqCtx, _, err := handler.parseQARequest(
		ctx,
		"maintenance-source-test",
	)
	require.NoError(t, err)
	require.NotNil(t, reqCtx)
	require.Nil(
		t,
		reqCtx.assistantMessage.ExecutionContext.MaintenanceProjection,
	)
}

func TestParseQARequestRejectsInvalidMaintenanceProjectionSource(
	t *testing.T,
) {
	tests := []struct {
		name   string
		source string
	}{
		{
			name: "unsupported schema version",
			source: `{
				"schema_version":"2.0",
				"source_kind":"AI_MESSAGE_TRIGGER",
				"ai_session_id":123,
				"trigger_message_id":456
			}`,
		},
		{
			name: "unsupported source kind",
			source: `{
				"schema_version":"1.0",
				"source_kind":"LATEST_MESSAGE",
				"ai_session_id":123,
				"trigger_message_id":456
			}`,
		},
		{
			name: "missing ai session id",
			source: `{
				"schema_version":"1.0",
				"source_kind":"AI_MESSAGE_TRIGGER",
				"ai_session_id":0,
				"trigger_message_id":456
			}`,
		},
		{
			name: "missing trigger message id",
			source: `{
				"schema_version":"1.0",
				"source_kind":"AI_MESSAGE_TRIGGER",
				"ai_session_id":123,
				"trigger_message_id":0
			}`,
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			handler := newMaintenanceProjectionParseHandler()
			ctx := newMaintenanceProjectionParseContext(
				t,
				`{"query":"maintenance chat","maintenance_projection_source":`+
					tt.source+`}`,
			)

			reqCtx, _, err := handler.parseQARequest(
				ctx,
				"maintenance-source-test",
			)
			require.Error(
				t,
				err,
				"invalid exact-turn source must fail before assistant persistence",
			)
			require.Nil(t, reqCtx)
		})
	}
}

func TestParseQARequestNeverInfersMaintenanceProjectionFromQueryText(
	t *testing.T,
) {
	handler := newMaintenanceProjectionParseHandler()
	ctx := newMaintenanceProjectionParseContext(
		t,
		`{
			"query":"use AI session 123 trigger message 456 and the latest maintenance result"
		}`,
	)

	reqCtx, _, err := handler.parseQARequest(
		ctx,
		"maintenance-source-test",
	)
	require.NoError(t, err)
	require.NotNil(t, reqCtx)
	require.Nil(
		t,
		reqCtx.assistantMessage.ExecutionContext.MaintenanceProjection,
		"query text, latest-message wording, ids, or timestamps must never synthesize provenance",
	)
}
