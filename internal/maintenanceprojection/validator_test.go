package maintenanceprojection

import (
	"encoding/json"
	"strings"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
	"github.com/stretchr/testify/require"
)

const (
	scenarioCardJSON = `{
		"schema_version":"1.0",
		"type":"SCENARIO_DRAFT",
		"title":"Scenario draft ready",
		"summary":"Review the persisted scenario draft.",
		"status":"PLANNED",
		"target":{
			"object_type":"AI_SESSION_SNAPSHOT",
			"object_id":123,
			"observed_version":2,
			"navigation_path":"/platform/maintenance/scenarios/new?session_id=123"
		},
		"observed_at":"2026-08-29T00:00:00Z",
		"payload":{}
	}`

	calculationCardJSON = `{
		"schema_version":"1.0",
		"type":"CALCULATION",
		"title":"Calculation created",
		"summary":"Open the calculation progress page.",
		"status":"PENDING",
		"target":{
			"object_type":"CALCULATION_GROUP",
			"object_id":35,
			"observed_version":1,
			"navigation_path":"/platform/maintenance/calculations/35/progress"
		},
		"observed_at":"2026-08-29T00:00:00Z",
		"payload":{
			"group_id":35,
			"scenario_version_id":7,
			"status":"PENDING",
			"primary_candidate_key":"base",
			"current_candidate_count":2,
			"observed_version":1
		}
	}`

	comparisonCardJSON = `{
		"schema_version":"1.0",
		"type":"MODEL_COMPARISON",
		"title":"Model comparison ready",
		"summary":"Compare the current calculation candidates.",
		"status":"READY",
		"target":{
			"object_type":"CALCULATION_GROUP",
			"object_id":35,
			"observed_version":1,
			"navigation_path":"/platform/maintenance/calculations/35/comparison"
		},
		"observed_at":"2026-08-29T00:00:00Z",
		"payload":{
			"group_id":35,
			"scenario_version_id":7,
			"comparable_candidate_count":2,
			"primary_candidate_key":"base",
			"observed_version":1
		}
	}`

	inventoryGapCardJSON = `{
		"schema_version":"1.0",
		"type":"INVENTORY_GAP",
		"title":"Inventory gap found",
		"summary":"Review allocation gaps and risks.",
		"status":"PREVIEWED",
		"target":{
			"object_type":"ALLOCATION_PLAN",
			"object_id":55,
			"observed_version":4,
			"navigation_path":"/platform/maintenance/inventory-gap/allocations/55"
		},
		"observed_at":"2026-08-29T00:00:00Z",
		"payload":{
			"gap_item_count":1,
			"total_gap_quantity":3.5,
			"risk_item_count":0,
			"source_demand_list_id":44,
			"plan_status":"PREVIEWED",
			"observed_version":4
		}
	}`

	reviewFindingCardJSON = `{
		"schema_version":"1.0",
		"type":"REVIEW_FINDING",
		"title":"Review finding requires attention",
		"summary":"Open the review to inspect the pending finding.",
		"status":"PENDING",
		"target":{
			"object_type":"DEMAND_REVIEW_FINDING",
			"object_id":77,
			"observed_version":8,
			"navigation_path":"/platform/maintenance/reviews/66"
		},
		"observed_at":"2026-08-29T00:00:00Z",
		"payload":{
			"finding_id":77,
			"review_id":66,
			"severity":"HIGH",
			"blocking":true,
			"remaining_pending_count":2,
			"observed_version":8
		}
	}`

	reportCardJSON = `{
		"schema_version":"1.0",
		"type":"REPORT",
		"title":"Report ready for review",
		"summary":"Open the report center to inspect the generated version.",
		"status":"READY_FOR_REVIEW",
		"target":{
			"object_type":"AI_REPORT_JOB",
			"object_id":88,
			"observed_version":3,
			"navigation_path":"/platform/maintenance/reports?report_id=88"
		},
		"observed_at":"2026-08-29T00:00:00Z",
		"payload":{
			"report_id":88,
			"report_code":"R-88",
			"report_type":"MANAGEMENT_DECISION",
			"job_status":"READY_FOR_REVIEW",
			"version_id":99,
			"version_number":3,
			"version_status":"DRAFT"
		}
	}`
)

func decodeCardMap(t *testing.T, raw string) map[string]any {
	t.Helper()

	var card map[string]any
	require.NoError(t, json.Unmarshal([]byte(raw), &card))
	return card
}

func encodeCardBatch(t *testing.T, cards ...map[string]any) []byte {
	t.Helper()

	raw, err := json.Marshal(cards)
	require.NoError(t, err)
	return raw
}

func cloneCardMap(t *testing.T, raw string) map[string]any {
	t.Helper()
	return decodeCardMap(t, raw)
}

func targetMap(t *testing.T, card map[string]any) map[string]any {
	t.Helper()

	target, ok := card["target"].(map[string]any)
	require.True(t, ok)
	return target
}

func testPayloadMap(t *testing.T, card map[string]any) map[string]any {
	t.Helper()

	payload, ok := card["payload"].(map[string]any)
	require.True(t, ok)
	return payload
}

func TestValidateAndCanonicalizeCardsAcceptsAllSixV1Types(t *testing.T) {
	fixtures := []string{
		scenarioCardJSON,
		calculationCardJSON,
		comparisonCardJSON,
		inventoryGapCardJSON,
		reviewFindingCardJSON,
		reportCardJSON,
	}

	for _, raw := range fixtures {
		card := decodeCardMap(t, raw)
		t.Run(card["type"].(string), func(t *testing.T) {
			cards, err := ValidateAndCanonicalizeCards(
				encodeCardBatch(t, card),
			)
			require.NoError(t, err)
			require.Len(t, cards, 1)
			require.Equal(t, card["type"], cards[0].Type)
		})
	}
}

func TestValidateAndCanonicalizeCardsRejectsUnsafeEnvelopeAndTarget(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{
			name: "unsupported schema",
			mutate: func(card map[string]any) {
				card["schema_version"] = "2.0"
			},
		},
		{
			name: "unsupported type",
			mutate: func(card map[string]any) {
				card["type"] = "UNKNOWN"
			},
		},
		{
			name: "wrong object type",
			mutate: func(card map[string]any) {
				targetMap(t, card)["object_type"] = "AI_SESSION_SNAPSHOT"
			},
		},
		{
			name: "missing object id",
			mutate: func(card map[string]any) {
				delete(targetMap(t, card), "object_id")
			},
		},
		{
			name: "boolean object id",
			mutate: func(card map[string]any) {
				targetMap(t, card)["object_id"] = true
			},
		},
		{
			name: "negative observed version",
			mutate: func(card map[string]any) {
				targetMap(t, card)["observed_version"] = -1
			},
		},
		{
			name: "external navigation",
			mutate: func(card map[string]any) {
				targetMap(t, card)["navigation_path"] =
					"https://example.com/calculations/35"
			},
		},
		{
			name: "wrong maintenance route",
			mutate: func(card map[string]any) {
				targetMap(t, card)["navigation_path"] =
					"/platform/maintenance/calculations/999/progress"
			},
		},
		{
			name: "timestamp without timezone",
			mutate: func(card map[string]any) {
				card["observed_at"] = "2026-08-29T00:00:00"
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			card := cloneCardMap(t, calculationCardJSON)
			tt.mutate(card)

			_, err := ValidateAndCanonicalizeCards(
				encodeCardBatch(t, card),
			)
			require.Error(t, err)
		})
	}
}

func TestValidateAndCanonicalizeCardsRejectsForbiddenAndMalformedPayloads(t *testing.T) {
	tests := []struct {
		name   string
		mutate func(map[string]any)
	}{
		{
			name: "top level confirmation token",
			mutate: func(card map[string]any) {
				card["confirmation_token"] = "forbidden"
			},
		},
		{
			name: "target tenant id",
			mutate: func(card map[string]any) {
				targetMap(t, card)["tenant_id"] = 9
			},
		},
		{
			name: "payload execute url",
			mutate: func(card map[string]any) {
				testPayloadMap(t, card)["execute_url"] =
					"/api/v1/demand/calculations/35/execute"
			},
		},
		{
			name: "missing required payload field",
			mutate: func(card map[string]any) {
				delete(testPayloadMap(t, card), "group_id")
			},
		},
		{
			name: "payload object mismatch",
			mutate: func(card map[string]any) {
				testPayloadMap(t, card)["group_id"] = 999
			},
		},
		{
			name: "payload version mismatch",
			mutate: func(card map[string]any) {
				testPayloadMap(t, card)["observed_version"] = 999
			},
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			card := cloneCardMap(t, calculationCardJSON)
			tt.mutate(card)

			_, err := ValidateAndCanonicalizeCards(
				encodeCardBatch(t, card),
			)
			require.Error(t, err)
		})
	}
}

func TestValidateAndCanonicalizeCardsEnforcesTextBounds(t *testing.T) {
	tests := []struct {
		name  string
		field string
		value string
	}{
		{"title", "title", strings.Repeat("t", 201)},
		{"summary", "summary", strings.Repeat("s", 1001)},
		{"status", "status", strings.Repeat("x", 65)},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			card := cloneCardMap(t, calculationCardJSON)
			card[tt.field] = tt.value

			_, err := ValidateAndCanonicalizeCards(
				encodeCardBatch(t, card),
			)
			require.Error(t, err)
		})
	}
}

func TestValidateAndCanonicalizeCardsStableSortsAndDeduplicatesExactIdentity(
	t *testing.T,
) {
	calculation := cloneCardMap(t, calculationCardJSON)
	scenario := cloneCardMap(t, scenarioCardJSON)
	review := cloneCardMap(t, reviewFindingCardJSON)
	calculationDuplicate := cloneCardMap(t, calculationCardJSON)

	first, err := ValidateAndCanonicalizeCards(
		encodeCardBatch(
			t,
			calculation,
			scenario,
			review,
			calculationDuplicate,
		),
	)
	require.NoError(t, err)
	require.Len(t, first, 3)
	require.Equal(
		t,
		[]string{"REVIEW_FINDING", "SCENARIO_DRAFT", "CALCULATION"},
		[]string{first[0].Type, first[1].Type, first[2].Type},
	)

	second, err := ValidateAndCanonicalizeCards(
		encodeCardBatch(
			t,
			cloneCardMap(t, reviewFindingCardJSON),
			cloneCardMap(t, calculationCardJSON),
			cloneCardMap(t, scenarioCardJSON),
		),
	)
	require.NoError(t, err)

	firstJSON, err := json.Marshal(first)
	require.NoError(t, err)
	secondJSON, err := json.Marshal(second)
	require.NoError(t, err)
	require.JSONEq(t, string(firstJSON), string(secondJSON))
	require.Equal(t, string(firstJSON), string(secondJSON))
}

func TestValidateAndCanonicalizeCardsRejectsMoreThanThreeDistinctCards(t *testing.T) {
	_, err := ValidateAndCanonicalizeCards(
		encodeCardBatch(
			t,
			cloneCardMap(t, reviewFindingCardJSON),
			cloneCardMap(t, inventoryGapCardJSON),
			cloneCardMap(t, scenarioCardJSON),
			cloneCardMap(t, calculationCardJSON),
		),
	)
	require.Error(t, err)
}

func TestValidateAndCanonicalizeCardsRejectsTwoDifferentCardsOfSameType(t *testing.T) {
	first := cloneCardMap(t, calculationCardJSON)
	second := cloneCardMap(t, calculationCardJSON)

	targetMap(t, second)["object_id"] = 36
	targetMap(t, second)["observed_version"] = 2
	targetMap(t, second)["navigation_path"] =
		"/platform/maintenance/calculations/36/progress"
	testPayloadMap(t, second)["group_id"] = 36
	testPayloadMap(t, second)["observed_version"] = 2

	_, err := ValidateAndCanonicalizeCards(
		encodeCardBatch(t, first, second),
	)
	require.Error(t, err)
}

func TestMaintenanceProjectionSizeCeilingIs32KiB(t *testing.T) {
	require.Equal(t, 32*1024, maxCardProjectionBytes)

	valid, err := ValidateAndCanonicalizeCards(
		encodeCardBatch(t, cloneCardMap(t, calculationCardJSON)),
	)
	require.NoError(t, err)
	require.NoError(t, requireProjectionSize(valid))

	oversized := types.MaintenanceCards{
		{
			SchemaVersion: "1.0",
			Type:          "CALCULATION",
			Title:         "oversized",
			Summary:       "oversized",
			Status:        "PENDING",
			Target: types.MaintenanceCardTarget{
				ObjectType:      "CALCULATION_GROUP",
				ObjectID:        35,
				ObservedVersion: 1,
				NavigationPath:  "/platform/maintenance/calculations/35/progress",
			},
			ObservedAt: "2026-08-29T00:00:00Z",
			Payload: map[string]any{
				"blob": strings.Repeat("x", 33*1024),
			},
		},
	}
	require.Error(t, requireProjectionSize(oversized))
}
