package maintenanceproxy

import (
	"crypto/rand"
	"errors"
	"fmt"
	"strings"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const internalTokenTTL = 180 * time.Second

// Signer creates short-lived HS256 tokens that bind an authenticated WeKnora
// actor to one tenant and request. A Signer is immutable after construction and
// safe for concurrent use except when tests replace the private clock.
type Signer struct {
	secret   []byte
	issuer   string
	audience string
	ttl      time.Duration
	now      func() time.Time
}

// NewSigner validates the internal-token contract and copies secret so later
// caller mutation cannot change the key used to sign requests.
func NewSigner(secret []byte, issuer, audience string, ttl time.Duration) (*Signer, error) {
	if len(secret) < 32 {
		return nil, errors.New("maintenance signing secret must contain at least 32 bytes")
	}

	issuer = strings.TrimSpace(issuer)
	if issuer == "" {
		return nil, errors.New("maintenance token issuer is required")
	}
	audience = strings.TrimSpace(audience)
	if audience == "" {
		return nil, errors.New("maintenance token audience is required")
	}
	if ttl != internalTokenTTL {
		return nil, errors.New("maintenance token TTL must be exactly 180 seconds")
	}

	return &Signer{
		secret:   append([]byte(nil), secret...),
		issuer:   issuer,
		audience: audience,
		ttl:      ttl,
		now:      time.Now,
	}, nil
}

// Sign validates and normalizes actor data, then emits a new token with a
// unique jti. The actor and its Roles slice are not modified.
func (s *Signer) Sign(actor Actor) (string, error) {
	if s == nil {
		return "", errors.New("maintenance token signer is nil")
	}

	userID := strings.TrimSpace(actor.UserID)
	if userID == "" {
		return "", errors.New("maintenance actor user_id is required")
	}
	tenantID := strings.TrimSpace(actor.TenantID)
	if tenantID == "" {
		return "", errors.New("maintenance actor tenant_id is required")
	}
	requestID := strings.TrimSpace(actor.RequestID)
	if requestID == "" {
		return "", errors.New("maintenance actor request_id is required")
	}
	roles, err := normalizeRoles(actor.Roles)
	if err != nil {
		return "", err
	}

	tokenID, err := newUUIDv4()
	if err != nil {
		return "", fmt.Errorf("generate maintenance token id: %w", err)
	}

	now := s.now().UTC()
	claims := Claims{
		TenantID:  tenantID,
		Roles:     roles,
		RequestID: requestID,
		RegisteredClaims: jwt.RegisteredClaims{
			Subject:   userID,
			Issuer:    s.issuer,
			Audience:  jwt.ClaimStrings{s.audience},
			IssuedAt:  jwt.NewNumericDate(now),
			ExpiresAt: jwt.NewNumericDate(now.Add(s.ttl)),
			ID:        tokenID,
		},
	}

	return jwt.NewWithClaims(jwt.SigningMethodHS256, claims).SignedString(s.secret)
}

func normalizeRoles(input []string) ([]string, error) {
	if len(input) == 0 {
		return nil, errors.New("maintenance actor requires at least one role")
	}

	roles := make([]string, 0, len(input))
	seen := make(map[string]struct{}, len(input))
	for _, raw := range input {
		role := strings.ToLower(strings.TrimSpace(raw))
		if role == "" {
			return nil, errors.New("maintenance actor role must not be blank")
		}
		if !isAllowedMaintenanceRole(role) {
			return nil, fmt.Errorf("unsupported maintenance role %q", role)
		}
		if _, duplicate := seen[role]; duplicate {
			continue
		}
		seen[role] = struct{}{}
		roles = append(roles, role)
	}
	return roles, nil
}

func isAllowedMaintenanceRole(role string) bool {
	switch role {
	case "viewer", "contributor", "admin":
		return true
	default:
		return false
	}
}

func newUUIDv4() (string, error) {
	var value [16]byte
	if _, err := rand.Read(value[:]); err != nil {
		return "", err
	}

	value[6] = (value[6] & 0x0f) | 0x40
	value[8] = (value[8] & 0x3f) | 0x80

	return fmt.Sprintf(
		"%08x-%04x-%04x-%04x-%012x",
		value[0:4],
		value[4:6],
		value[6:8],
		value[8:10],
		value[10:16],
	), nil
}
