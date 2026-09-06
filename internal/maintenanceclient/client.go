package maintenanceclient

import (
	"bytes"
	"context"
	"encoding/json"
	"errors"
	"fmt"
	"io"
	"net/http"
	"net/url"
	"strconv"
	"strings"

	"github.com/Tencent/WeKnora/internal/config"
	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
)

const maxProjectionResponseBytes = 128 * 1024

// Client reads validated Maintenance projections for one exact persisted
// Maintenance AI trigger turn.
type Client struct {
	baseURL    string
	httpClient *http.Client
	signer     *maintenanceproxy.Signer
}

// New creates the narrow server-to-server Maintenance projection client.
func New(
	cfg *config.MaintenanceConfig,
	signer *maintenanceproxy.Signer,
) (*Client, error) {
	if cfg == nil {
		return nil, errors.New("maintenance config is nil")
	}
	if !cfg.Enabled {
		return nil, errors.New("maintenance integration is disabled")
	}
	if signer == nil {
		return nil, errors.New("maintenance signer is nil")
	}
	if cfg.RequestTimeout <= 0 {
		return nil, errors.New("maintenance request timeout must be positive")
	}

	parsed, err := url.Parse(cfg.BaseURL)
	if err != nil ||
		parsed.Scheme == "" ||
		parsed.Host == "" ||
		parsed.User != nil ||
		parsed.RawQuery != "" ||
		parsed.Fragment != "" {
		return nil, errors.New(
			"maintenance base URL must be an absolute HTTP(S) URL without userinfo, query, or fragment",
		)
	}
	if parsed.Scheme != "http" && parsed.Scheme != "https" {
		return nil, errors.New("maintenance base URL must use http or https")
	}

	return &Client{
		baseURL: strings.TrimRight(parsed.String(), "/"),
		httpClient: &http.Client{
			Timeout: cfg.RequestTimeout,
		},
		signer: signer,
	}, nil
}

// RecoverExactTurn resolves the read-only projection for exactly one persisted
// Maintenance AI trigger turn. It never performs latest-turn discovery.
func (c *Client) RecoverExactTurn(
	ctx context.Context,
	actor maintenanceproxy.Actor,
	source types.MaintenanceProjectionProvenance,
) (types.MaintenanceCards, error) {
	if c == nil {
		return nil, errors.New("maintenance client is nil")
	}
	if err := validateSource(source); err != nil {
		return nil, err
	}

	token, err := c.signer.Sign(actor)
	if err != nil {
		return nil, fmt.Errorf("sign maintenance request: %w", err)
	}

	path := "/api/v1/ai/sessions/" +
		strconv.FormatInt(source.AISessionID, 10) +
		"/messages/" +
		strconv.FormatInt(source.TriggerMessageID, 10) +
		"/business-cards"

	req, err := http.NewRequestWithContext(
		ctx,
		http.MethodGet,
		c.baseURL+path,
		nil,
	)
	if err != nil {
		return nil, fmt.Errorf("create maintenance request: %w", err)
	}
	req.Header.Set("Authorization", "Bearer "+token)
	req.Header.Set("X-Request-ID", strings.TrimSpace(actor.RequestID))
	req.Header.Set("Accept", "application/json")

	resp, err := c.httpClient.Do(req)
	if err != nil {
		if ctx.Err() != nil {
			return nil, ctx.Err()
		}
		return nil, fmt.Errorf("maintenance projection request failed: %w", err)
	}
	defer resp.Body.Close()

	if resp.StatusCode < http.StatusOK ||
		resp.StatusCode >= http.StatusMultipleChoices {
		return nil, fmt.Errorf(
			"maintenance projection request returned HTTP %d",
			resp.StatusCode,
		)
	}

	body, err := io.ReadAll(
		io.LimitReader(resp.Body, maxProjectionResponseBytes+1),
	)
	if err != nil {
		return nil, fmt.Errorf("read maintenance projection response: %w", err)
	}
	if len(body) > maxProjectionResponseBytes {
		return nil, errors.New("maintenance projection response exceeds limit")
	}

	var envelope struct {
		Data json.RawMessage `json:"data"`
	}
	if err := json.Unmarshal(body, &envelope); err != nil {
		return nil, fmt.Errorf("decode maintenance response envelope: %w", err)
	}
	if len(bytes.TrimSpace(envelope.Data)) == 0 ||
		bytes.Equal(bytes.TrimSpace(envelope.Data), []byte("null")) {
		return nil, errors.New("maintenance response is missing projection data")
	}

	var projection struct {
		SchemaVersion string `json:"schema_version"`
		Source        struct {
			Kind      string `json:"kind"`
			SessionID int64  `json:"session_id"`
			MessageID int64  `json:"message_id"`
		} `json:"source"`
		Cards json.RawMessage `json:"cards"`
	}
	decoder := json.NewDecoder(bytes.NewReader(envelope.Data))
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(&projection); err != nil {
		return nil, fmt.Errorf("decode maintenance projection: %w", err)
	}
	if projection.SchemaVersion != source.SchemaVersion ||
		projection.Source.Kind != source.SourceKind ||
		projection.Source.SessionID != source.AISessionID ||
		projection.Source.MessageID != source.TriggerMessageID {
		return nil, errors.New("maintenance projection source identity mismatch")
	}

	if len(bytes.TrimSpace(projection.Cards)) == 0 {
		return nil, errors.New("maintenance projection is missing cards")
	}
	cards, err := maintenanceprojection.ValidateAndCanonicalizeCards(
		projection.Cards,
	)
	if err != nil {
		return nil, fmt.Errorf(
			"core maintenance projection validation failed: %w",
			err,
		)
	}
	return cards, nil
}

func validateSource(source types.MaintenanceProjectionProvenance) error {
	if source.SchemaVersion != "1.0" {
		return errors.New("unsupported maintenance projection source schema")
	}
	if source.SourceKind != "AI_MESSAGE_TRIGGER" {
		return errors.New("unsupported maintenance projection source kind")
	}
	if source.AISessionID <= 0 {
		return errors.New("maintenance ai_session_id must be positive")
	}
	if source.TriggerMessageID <= 0 {
		return errors.New("maintenance trigger_message_id must be positive")
	}
	return nil
}
