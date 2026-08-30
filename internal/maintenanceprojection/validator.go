package maintenanceprojection

import (
	"bytes"
	"encoding/json"
	"fmt"
	"io"
	"net/url"
	"sort"
	"strconv"
	"strings"
	"time"
	"unicode/utf8"

	"github.com/Tencent/WeKnora/internal/types"
)

const (
	cardSchemaVersion      = "1.0"
	maxCardTitleChars      = 200
	maxCardSummaryChars    = 1000
	maxCardStatusChars     = 64
	maxCardNavigationChars = 500
	maxCardsPerMessage     = 3
	maxCardProjectionBytes = 32 * 1024
)

var cardPriority = map[string]int{
	"REVIEW_FINDING":   0,
	"INVENTORY_GAP":    1,
	"SCENARIO_DRAFT":   2,
	"CALCULATION":      3,
	"MODEL_COMPARISON": 4,
	"REPORT":           5,
}

var expectedObjectType = map[string]string{
	"SCENARIO_DRAFT":   "AI_SESSION_SNAPSHOT",
	"CALCULATION":      "CALCULATION_GROUP",
	"MODEL_COMPARISON": "CALCULATION_GROUP",
	"INVENTORY_GAP":    "ALLOCATION_PLAN",
	"REVIEW_FINDING":   "DEMAND_REVIEW_FINDING",
	"REPORT":           "AI_REPORT_JOB",
}

type cardTargetDTO struct {
	ObjectType      string          `json:"object_type"`
	ObjectID        json.RawMessage `json:"object_id"`
	ObservedVersion json.RawMessage `json:"observed_version"`
	NavigationPath  string          `json:"navigation_path"`
}

type cardEnvelope[P any] struct {
	SchemaVersion string        `json:"schema_version"`
	Type          string        `json:"type"`
	Title         string        `json:"title"`
	Summary       string        `json:"summary"`
	Status        string        `json:"status"`
	Target        cardTargetDTO `json:"target"`
	ObservedAt    string        `json:"observed_at"`
	Payload       P             `json:"payload"`
}

type scenarioDraftPayload struct{}

type calculationPayload struct {
	GroupID               int64           `json:"group_id"`
	ScenarioVersionID     int64           `json:"scenario_version_id"`
	Status                string          `json:"status"`
	PrimaryCandidateKey   *string         `json:"primary_candidate_key"`
	CurrentCandidateCount int64           `json:"current_candidate_count"`
	ObservedVersion       json.RawMessage `json:"observed_version"`
}

type modelComparisonPayload struct {
	GroupID                  int64           `json:"group_id"`
	ScenarioVersionID        int64           `json:"scenario_version_id"`
	ComparableCandidateCount int64           `json:"comparable_candidate_count"`
	PrimaryCandidateKey      *string         `json:"primary_candidate_key"`
	ObservedVersion          json.RawMessage `json:"observed_version"`
}

type inventoryGapPayload struct {
	GapItemCount       int64           `json:"gap_item_count"`
	TotalGapQuantity   json.Number     `json:"total_gap_quantity"`
	RiskItemCount      int64           `json:"risk_item_count"`
	SourceDemandListID int64           `json:"source_demand_list_id"`
	PlanStatus         string          `json:"plan_status"`
	ObservedVersion    json.RawMessage `json:"observed_version"`
}

type reviewFindingPayload struct {
	FindingID             int64           `json:"finding_id"`
	ReviewID              int64           `json:"review_id"`
	Severity              string          `json:"severity"`
	Blocking              *bool           `json:"blocking"`
	RemainingPendingCount int64           `json:"remaining_pending_count"`
	ObservedVersion       json.RawMessage `json:"observed_version"`
}

type reportPayload struct {
	ReportID      int64  `json:"report_id"`
	ReportCode    string `json:"report_code"`
	ReportType    string `json:"report_type"`
	JobStatus     string `json:"job_status"`
	VersionID     int64  `json:"version_id"`
	VersionNumber int64  `json:"version_number"`
	VersionStatus string `json:"version_status"`
}

// ValidateAndCanonicalizeCards performs the Core structural/safety validation
// required before a Maintenance projection is persisted on a Message.
func ValidateAndCanonicalizeCards(raw []byte) (types.MaintenanceCards, error) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return nil, fmt.Errorf("maintenance card projection must be a JSON array")
	}

	var items []json.RawMessage
	if err := json.Unmarshal(trimmed, &items); err != nil {
		return nil, fmt.Errorf("decode maintenance card projection: %w", err)
	}
	if items == nil {
		return nil, fmt.Errorf("maintenance card projection must be a JSON array")
	}

	cards := make(types.MaintenanceCards, 0, len(items))
	for _, item := range items {
		card, err := parseCard(item)
		if err != nil {
			return nil, err
		}
		cards = append(cards, card)
	}
	return canonicalizeCards(cards)
}

func parseCard(raw json.RawMessage) (types.MaintenanceCard, error) {
	var selector struct {
		Type string `json:"type"`
	}
	if err := json.Unmarshal(raw, &selector); err != nil {
		return types.MaintenanceCard{}, fmt.Errorf("decode maintenance card type: %w", err)
	}

	switch selector.Type {
	case "SCENARIO_DRAFT":
		return parseScenarioDraftCard(raw)
	case "CALCULATION":
		return parseCalculationCard(raw)
	case "MODEL_COMPARISON":
		return parseModelComparisonCard(raw)
	case "INVENTORY_GAP":
		return parseInventoryGapCard(raw)
	case "REVIEW_FINDING":
		return parseReviewFindingCard(raw)
	case "REPORT":
		return parseReportCard(raw)
	default:
		return types.MaintenanceCard{}, fmt.Errorf("unsupported maintenance card type %q", selector.Type)
	}
}

func parseScenarioDraftCard(raw json.RawMessage) (types.MaintenanceCard, error) {
	envelope, card, err := decodeEnvelope[scenarioDraftPayload](raw, "SCENARIO_DRAFT")
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireQueryNavigation(
		envelope.Target.NavigationPath,
		"/platform/maintenance/scenarios/new",
		"session_id",
		card.Target.ObjectID,
	); err != nil {
		return types.MaintenanceCard{}, err
	}
	return card, nil
}

func parseCalculationCard(raw json.RawMessage) (types.MaintenanceCard, error) {
	envelope, card, err := decodeEnvelope[calculationPayload](raw, "CALCULATION")
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	p := envelope.Payload
	if p.GroupID <= 0 || p.ScenarioVersionID <= 0 || p.CurrentCandidateCount < 0 {
		return types.MaintenanceCard{}, fmt.Errorf("invalid CALCULATION payload")
	}
	if err := validateBoundedString("payload.status", p.Status, maxCardStatusChars); err != nil {
		return types.MaintenanceCard{}, err
	}
	if p.PrimaryCandidateKey != nil && utf8.RuneCountInString(*p.PrimaryCandidateKey) > 128 {
		return types.MaintenanceCard{}, fmt.Errorf("payload.primary_candidate_key exceeds 128 characters")
	}
	if fmt.Sprint(p.GroupID) != fmt.Sprint(card.Target.ObjectID) {
		return types.MaintenanceCard{}, fmt.Errorf("CALCULATION payload.group_id must match target.object_id")
	}
	payloadVersion, err := parseObservedVersion(p.ObservedVersion)
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireVersionMatch(card.Target.ObservedVersion, payloadVersion); err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireExactNavigation(
		envelope.Target.NavigationPath,
		fmt.Sprintf("/platform/maintenance/calculations/%v/progress", card.Target.ObjectID),
	); err != nil {
		return types.MaintenanceCard{}, err
	}
	return card, nil
}

func parseModelComparisonCard(raw json.RawMessage) (types.MaintenanceCard, error) {
	envelope, card, err := decodeEnvelope[modelComparisonPayload](raw, "MODEL_COMPARISON")
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	p := envelope.Payload
	if p.GroupID <= 0 || p.ScenarioVersionID <= 0 || p.ComparableCandidateCount < 2 {
		return types.MaintenanceCard{}, fmt.Errorf("invalid MODEL_COMPARISON payload")
	}
	if p.PrimaryCandidateKey != nil && utf8.RuneCountInString(*p.PrimaryCandidateKey) > 128 {
		return types.MaintenanceCard{}, fmt.Errorf("payload.primary_candidate_key exceeds 128 characters")
	}
	if fmt.Sprint(p.GroupID) != fmt.Sprint(card.Target.ObjectID) {
		return types.MaintenanceCard{}, fmt.Errorf("MODEL_COMPARISON payload.group_id must match target.object_id")
	}
	payloadVersion, err := parseObservedVersion(p.ObservedVersion)
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireVersionMatch(card.Target.ObservedVersion, payloadVersion); err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireExactNavigation(
		envelope.Target.NavigationPath,
		fmt.Sprintf("/platform/maintenance/calculations/%v/comparison", card.Target.ObjectID),
	); err != nil {
		return types.MaintenanceCard{}, err
	}
	return card, nil
}

func parseInventoryGapCard(raw json.RawMessage) (types.MaintenanceCard, error) {
	envelope, card, err := decodeEnvelope[inventoryGapPayload](raw, "INVENTORY_GAP")
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	p := envelope.Payload
	if p.GapItemCount < 0 || p.RiskItemCount < 0 || p.SourceDemandListID <= 0 {
		return types.MaintenanceCard{}, fmt.Errorf("invalid INVENTORY_GAP payload")
	}
	quantity, err := strconv.ParseFloat(string(p.TotalGapQuantity), 64)
	if err != nil || quantity < 0 {
		return types.MaintenanceCard{}, fmt.Errorf("invalid INVENTORY_GAP total_gap_quantity")
	}
	if p.GapItemCount == 0 && p.RiskItemCount == 0 {
		return types.MaintenanceCard{}, fmt.Errorf("INVENTORY_GAP requires a gap or meaningful risk")
	}
	if err := validateBoundedString("payload.plan_status", p.PlanStatus, maxCardStatusChars); err != nil {
		return types.MaintenanceCard{}, err
	}
	payloadVersion, err := parseObservedVersion(p.ObservedVersion)
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireVersionMatch(card.Target.ObservedVersion, payloadVersion); err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireExactNavigation(
		envelope.Target.NavigationPath,
		fmt.Sprintf("/platform/maintenance/inventory-gap/allocations/%v", card.Target.ObjectID),
	); err != nil {
		return types.MaintenanceCard{}, err
	}
	return card, nil
}

func parseReviewFindingCard(raw json.RawMessage) (types.MaintenanceCard, error) {
	envelope, card, err := decodeEnvelope[reviewFindingPayload](raw, "REVIEW_FINDING")
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	p := envelope.Payload
	if p.FindingID <= 0 || p.ReviewID <= 0 || p.RemainingPendingCount < 0 || p.Blocking == nil {
		return types.MaintenanceCard{}, fmt.Errorf("invalid REVIEW_FINDING payload")
	}
	switch p.Severity {
	case "LOW", "MEDIUM", "HIGH", "CRITICAL":
	default:
		return types.MaintenanceCard{}, fmt.Errorf("invalid REVIEW_FINDING severity")
	}
	if fmt.Sprint(p.FindingID) != fmt.Sprint(card.Target.ObjectID) {
		return types.MaintenanceCard{}, fmt.Errorf("REVIEW_FINDING payload.finding_id must match target.object_id")
	}
	payloadVersion, err := parseObservedVersion(p.ObservedVersion)
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireVersionMatch(card.Target.ObservedVersion, payloadVersion); err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := requireExactNavigation(
		envelope.Target.NavigationPath,
		fmt.Sprintf("/platform/maintenance/reviews/%d", p.ReviewID),
	); err != nil {
		return types.MaintenanceCard{}, err
	}
	return card, nil
}

func parseReportCard(raw json.RawMessage) (types.MaintenanceCard, error) {
	envelope, card, err := decodeEnvelope[reportPayload](raw, "REPORT")
	if err != nil {
		return types.MaintenanceCard{}, err
	}
	p := envelope.Payload
	if p.ReportID <= 0 || p.VersionID <= 0 || p.VersionNumber < 1 {
		return types.MaintenanceCard{}, fmt.Errorf("invalid REPORT payload")
	}
	if err := validateBoundedString("payload.report_code", p.ReportCode, 64); err != nil {
		return types.MaintenanceCard{}, err
	}
	switch p.ReportType {
	case "DEMAND_CALCULATION", "INVENTORY_GAP", "MANAGEMENT_DECISION":
	default:
		return types.MaintenanceCard{}, fmt.Errorf("invalid REPORT report_type")
	}
	if err := validateBoundedString("payload.job_status", p.JobStatus, maxCardStatusChars); err != nil {
		return types.MaintenanceCard{}, err
	}
	if err := validateBoundedString("payload.version_status", p.VersionStatus, maxCardStatusChars); err != nil {
		return types.MaintenanceCard{}, err
	}
	if fmt.Sprint(p.ReportID) != fmt.Sprint(card.Target.ObjectID) {
		return types.MaintenanceCard{}, fmt.Errorf("REPORT payload.report_id must match target.object_id")
	}
	if card.Target.ObservedVersion != nil && fmt.Sprint(card.Target.ObservedVersion) != fmt.Sprint(p.VersionNumber) {
		return types.MaintenanceCard{}, fmt.Errorf("REPORT observed_version must match payload.version_number")
	}
	if err := requireQueryNavigation(
		envelope.Target.NavigationPath,
		"/platform/maintenance/reports",
		"report_id",
		card.Target.ObjectID,
	); err != nil {
		return types.MaintenanceCard{}, err
	}
	return card, nil
}

func decodeEnvelope[P any](
	raw json.RawMessage,
	expectedType string,
) (cardEnvelope[P], types.MaintenanceCard, error) {
	var envelope cardEnvelope[P]
	if err := decodeStrict(raw, &envelope); err != nil {
		return envelope, types.MaintenanceCard{}, fmt.Errorf("invalid %s card: %w", expectedType, err)
	}
	if envelope.SchemaVersion != cardSchemaVersion {
		return envelope, types.MaintenanceCard{}, fmt.Errorf("unsupported maintenance card schema %q", envelope.SchemaVersion)
	}
	if envelope.Type != expectedType {
		return envelope, types.MaintenanceCard{}, fmt.Errorf("maintenance card type mismatch")
	}
	if err := validateBoundedString("title", envelope.Title, maxCardTitleChars); err != nil {
		return envelope, types.MaintenanceCard{}, err
	}
	if err := validateBoundedString("summary", envelope.Summary, maxCardSummaryChars); err != nil {
		return envelope, types.MaintenanceCard{}, err
	}
	if err := validateBoundedString("status", envelope.Status, maxCardStatusChars); err != nil {
		return envelope, types.MaintenanceCard{}, err
	}
	if expected := expectedObjectType[expectedType]; envelope.Target.ObjectType != expected {
		return envelope, types.MaintenanceCard{}, fmt.Errorf("%s target.object_type must be %s", expectedType, expected)
	}
	objectID, err := parseObjectIdentity(envelope.Target.ObjectID)
	if err != nil {
		return envelope, types.MaintenanceCard{}, err
	}
	observedVersion, err := parseObservedVersion(envelope.Target.ObservedVersion)
	if err != nil {
		return envelope, types.MaintenanceCard{}, err
	}
	if err := validateBoundedString("navigation_path", envelope.Target.NavigationPath, maxCardNavigationChars); err != nil {
		return envelope, types.MaintenanceCard{}, err
	}
	if _, err := time.Parse(time.RFC3339, envelope.ObservedAt); err != nil {
		return envelope, types.MaintenanceCard{}, fmt.Errorf("observed_at must be RFC3339 with timezone")
	}
	payload, err := payloadMap(raw)
	if err != nil {
		return envelope, types.MaintenanceCard{}, err
	}

	card := types.MaintenanceCard{
		SchemaVersion: envelope.SchemaVersion,
		Type:          envelope.Type,
		Title:         envelope.Title,
		Summary:       envelope.Summary,
		Status:        envelope.Status,
		Target: types.MaintenanceCardTarget{
			ObjectType:      envelope.Target.ObjectType,
			ObjectID:        objectID,
			ObservedVersion: observedVersion,
			NavigationPath:  envelope.Target.NavigationPath,
		},
		ObservedAt: envelope.ObservedAt,
		Payload:    payload,
	}
	return envelope, card, nil
}

func decodeStrict(raw []byte, out any) error {
	decoder := json.NewDecoder(bytes.NewReader(raw))
	decoder.DisallowUnknownFields()
	decoder.UseNumber()
	if err := decoder.Decode(out); err != nil {
		return err
	}
	if err := decoder.Decode(&struct{}{}); err != io.EOF {
		if err == nil {
			return fmt.Errorf("unexpected trailing JSON value")
		}
		return err
	}
	return nil
}

func payloadMap(raw json.RawMessage) (map[string]any, error) {
	var fields map[string]json.RawMessage
	if err := json.Unmarshal(raw, &fields); err != nil {
		return nil, err
	}
	payloadRaw, exists := fields["payload"]
	if !exists {
		return map[string]any{}, nil
	}
	if bytes.Equal(bytes.TrimSpace(payloadRaw), []byte("null")) {
		return nil, fmt.Errorf("payload must be an object")
	}
	var payload map[string]any
	decoder := json.NewDecoder(bytes.NewReader(payloadRaw))
	decoder.UseNumber()
	if err := decoder.Decode(&payload); err != nil {
		return nil, fmt.Errorf("decode maintenance card payload: %w", err)
	}
	if payload == nil {
		return nil, fmt.Errorf("payload must be an object")
	}
	return payload, nil
}

func parseObjectIdentity(raw json.RawMessage) (any, error) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return nil, fmt.Errorf("target.object_id is required")
	}
	if trimmed[0] == '"' {
		var value string
		if err := json.Unmarshal(trimmed, &value); err != nil {
			return nil, fmt.Errorf("invalid target.object_id")
		}
		if strings.TrimSpace(value) == "" {
			return nil, fmt.Errorf("target.object_id string must be non-empty")
		}
		return value, nil
	}
	value, err := strconv.ParseInt(string(trimmed), 10, 64)
	if err != nil || value <= 0 {
		return nil, fmt.Errorf("target.object_id must be a positive integer or non-empty string")
	}
	return value, nil
}

func parseObservedVersion(raw json.RawMessage) (any, error) {
	trimmed := bytes.TrimSpace(raw)
	if len(trimmed) == 0 || bytes.Equal(trimmed, []byte("null")) {
		return nil, nil
	}
	if trimmed[0] == '"' {
		var value string
		if err := json.Unmarshal(trimmed, &value); err != nil {
			return nil, fmt.Errorf("invalid observed_version")
		}
		if strings.TrimSpace(value) == "" {
			return nil, fmt.Errorf("observed_version string must be non-empty")
		}
		return value, nil
	}
	value, err := strconv.ParseInt(string(trimmed), 10, 64)
	if err != nil || value < 0 {
		return nil, fmt.Errorf("observed_version must be a non-negative integer, non-empty string, or null")
	}
	return value, nil
}

func validateBoundedString(name, value string, maxChars int) error {
	count := utf8.RuneCountInString(value)
	if count == 0 {
		return fmt.Errorf("%s must be non-empty", name)
	}
	if count > maxChars {
		return fmt.Errorf("%s exceeds %d characters", name, maxChars)
	}
	return nil
}

func requireExactNavigation(actual, expected string) error {
	if actual != expected {
		return fmt.Errorf("navigation_path does not match the card route template")
	}
	return nil
}

func requireQueryNavigation(actual, expectedPath, queryKey string, objectID any) error {
	parsed, err := url.Parse(actual)
	if err != nil || parsed.Scheme != "" || parsed.Host != "" || parsed.User != nil || parsed.Fragment != "" || parsed.Path != expectedPath {
		return fmt.Errorf("navigation_path must be a fixed same-origin maintenance path")
	}
	query, err := url.ParseQuery(parsed.RawQuery)
	if err != nil || len(query) != 1 {
		return fmt.Errorf("navigation_path does not match the card route template")
	}
	values, ok := query[queryKey]
	if !ok || len(values) != 1 || values[0] != fmt.Sprint(objectID) {
		return fmt.Errorf("navigation_path does not match the card route template")
	}
	return nil
}

func requireVersionMatch(targetVersion, payloadVersion any) error {
	if targetVersion == nil || payloadVersion == nil {
		return nil
	}
	if fmt.Sprint(targetVersion) != fmt.Sprint(payloadVersion) {
		return fmt.Errorf("payload observed_version must match target.observed_version")
	}
	return nil
}

func canonicalizeCards(cards types.MaintenanceCards) (types.MaintenanceCards, error) {
	byIdentity := make(map[string]types.MaintenanceCard, len(cards))
	order := make([]string, 0, len(cards))
	for _, card := range cards {
		key := cardIdentity(card)
		if _, exists := byIdentity[key]; exists {
			continue
		}
		byIdentity[key] = card
		order = append(order, key)
	}

	deduped := make(types.MaintenanceCards, 0, len(order))
	seenTypes := make(map[string]struct{}, len(order))
	for _, key := range order {
		card := byIdentity[key]
		if _, exists := seenTypes[card.Type]; exists {
			return nil, fmt.Errorf("only one %s card is allowed per message", card.Type)
		}
		seenTypes[card.Type] = struct{}{}
		deduped = append(deduped, card)
	}
	if len(deduped) > maxCardsPerMessage {
		return nil, fmt.Errorf("at most %d maintenance cards are allowed per message", maxCardsPerMessage)
	}

	sort.SliceStable(deduped, func(i, j int) bool {
		left, right := deduped[i], deduped[j]
		if cardPriority[left.Type] != cardPriority[right.Type] {
			return cardPriority[left.Type] < cardPriority[right.Type]
		}
		if left.Target.ObjectType != right.Target.ObjectType {
			return left.Target.ObjectType < right.Target.ObjectType
		}
		if fmt.Sprint(left.Target.ObjectID) != fmt.Sprint(right.Target.ObjectID) {
			return fmt.Sprint(left.Target.ObjectID) < fmt.Sprint(right.Target.ObjectID)
		}
		return fmt.Sprint(left.Target.ObservedVersion) < fmt.Sprint(right.Target.ObservedVersion)
	})

	if err := requireProjectionSize(deduped); err != nil {
		return nil, err
	}
	return deduped, nil
}

func cardIdentity(card types.MaintenanceCard) string {
	return strings.Join([]string{
		card.Type,
		card.Target.ObjectType,
		fmt.Sprint(card.Target.ObjectID),
		fmt.Sprint(card.Target.ObservedVersion),
	}, "\x00")
}

func requireProjectionSize(cards types.MaintenanceCards) error {
	raw, err := json.Marshal(cards)
	if err != nil {
		return fmt.Errorf("serialize maintenance card projection: %w", err)
	}
	if len(raw) > maxCardProjectionBytes {
		return fmt.Errorf("maintenance card projection exceeds %d bytes", maxCardProjectionBytes)
	}
	return nil
}
