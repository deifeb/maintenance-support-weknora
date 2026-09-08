package maintenanceprojectioncontract_test

import (
	"encoding/json"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/require"
)

func TestMessageExecutionContextRoundTripsExactMaintenanceProjectionProvenance(
	t *testing.T,
) {
	executionContext := types.MessageExecutionContext{
		MaintenanceProjection: &types.MaintenanceProjectionProvenance{
			SchemaVersion:    "1.0",
			SourceKind:       "AI_MESSAGE_TRIGGER",
			AISessionID:      123,
			TriggerMessageID: 456,
		},
	}

	value, err := executionContext.Value()
	require.NoError(t, err)

	var scanned types.MessageExecutionContext
	require.NoError(t, scanned.Scan(value))

	require.NotNil(t, scanned.MaintenanceProjection)
	require.Equal(t, "1.0", scanned.MaintenanceProjection.SchemaVersion)
	require.Equal(
		t,
		"AI_MESSAGE_TRIGGER",
		scanned.MaintenanceProjection.SourceKind,
	)
	require.EqualValues(
		t,
		123,
		scanned.MaintenanceProjection.AISessionID,
	)
	require.EqualValues(
		t,
		456,
		scanned.MaintenanceProjection.TriggerMessageID,
	)

	raw, err := json.Marshal(scanned)
	require.NoError(t, err)

	var decoded map[string]any
	require.NoError(t, json.Unmarshal(raw, &decoded))

	projection, ok := decoded["maintenance_projection"].(map[string]any)
	require.True(t, ok)

	require.Equal(t, "1.0", projection["schema_version"])
	require.Equal(
		t,
		"AI_MESSAGE_TRIGGER",
		projection["source_kind"],
	)
	require.EqualValues(t, 123, projection["ai_session_id"])
	require.EqualValues(t, 456, projection["trigger_message_id"])

	serialized := string(raw)
	require.NotContains(t, serialized, `"tenant_id"`)
	require.NotContains(t, serialized, `"authorization"`)
	require.NotContains(t, serialized, `"signing_secret"`)
	require.NotContains(t, serialized, `"confirmation_token"`)
	require.NotContains(t, serialized, `"cards"`)
}

func TestEmptyExecutionContextOmitsMaintenanceProjectionProvenance(
	t *testing.T,
) {
	executionContext := types.MessageExecutionContext{}

	raw, err := json.Marshal(executionContext)
	require.NoError(t, err)
	require.NotContains(t, string(raw), `"maintenance_projection"`)
}
