package maintenanceproxy

import (
	"reflect"
	"regexp"
	"strings"
	"testing"
	"time"

	"github.com/golang-jwt/jwt/v5"
)

const testSigningSecret = "01234567890123456789012345678901"

func TestSignerCreatesBoundShortLivedToken(t *testing.T) {
	now := time.Unix(1_784_894_400, 0).UTC()
	signer, err := NewSigner([]byte(testSigningSecret), " weknora ", " maintenance-api ", 180*time.Second)
	if err != nil {
		t.Fatalf("NewSigner() error = %v", err)
	}
	signer.now = func() time.Time { return now }

	roles := []string{" Contributor ", "viewer", "contributor"}
	originalRoles := append([]string(nil), roles...)
	tokenString, err := signer.Sign(Actor{
		UserID:    " u-1 ",
		TenantID:  " t-1 ",
		Roles:     roles,
		RequestID: " r-1 ",
	})
	if err != nil {
		t.Fatalf("Sign() error = %v", err)
	}
	if !reflect.DeepEqual(roles, originalRoles) {
		t.Fatalf("Sign() mutated actor roles: got %v want %v", roles, originalRoles)
	}

	parsed, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (any, error) {
		if token.Method != jwt.SigningMethodHS256 {
			t.Fatalf("signing method = %v, want HS256", token.Method)
		}
		return []byte(testSigningSecret), nil
	}, jwt.WithValidMethods([]string{"HS256"}), jwt.WithAudience("maintenance-api"), jwt.WithIssuer("weknora"), jwt.WithTimeFunc(func() time.Time { return now }))
	if err != nil {
		t.Fatalf("ParseWithClaims() error = %v", err)
	}
	if !parsed.Valid {
		t.Fatal("parsed token is not valid")
	}

	claims, ok := parsed.Claims.(*Claims)
	if !ok {
		t.Fatalf("claims type = %T, want *Claims", parsed.Claims)
	}
	if claims.Subject != "u-1" {
		t.Fatalf("subject = %q, want u-1", claims.Subject)
	}
	if claims.TenantID != "t-1" {
		t.Fatalf("tenant_id = %q, want t-1", claims.TenantID)
	}
	if !reflect.DeepEqual(claims.Roles, []string{"contributor", "viewer"}) {
		t.Fatalf("roles = %v, want [contributor viewer]", claims.Roles)
	}
	if claims.RequestID != "r-1" {
		t.Fatalf("request_id = %q, want r-1", claims.RequestID)
	}
	if claims.Issuer != "weknora" {
		t.Fatalf("issuer = %q, want weknora", claims.Issuer)
	}
	if !reflect.DeepEqual([]string(claims.Audience), []string{"maintenance-api"}) {
		t.Fatalf("audience = %v, want [maintenance-api]", claims.Audience)
	}
	if claims.IssuedAt == nil || !claims.IssuedAt.Time.Equal(now) {
		t.Fatalf("issued_at = %v, want %v", claims.IssuedAt, now)
	}
	if claims.ExpiresAt == nil || !claims.ExpiresAt.Time.Equal(now.Add(180*time.Second)) {
		t.Fatalf("expires_at = %v, want %v", claims.ExpiresAt, now.Add(180*time.Second))
	}
	if !regexp.MustCompile(`^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$`).MatchString(claims.ID) {
		t.Fatalf("jti = %q, want UUIDv4", claims.ID)
	}
}

func TestNewSignerRejectsInvalidConfiguration(t *testing.T) {
	tests := []struct {
		name     string
		secret   string
		issuer   string
		audience string
		ttl      time.Duration
		want     string
	}{
		{name: "short secret", secret: "short", issuer: "weknora", audience: "maintenance-api", ttl: 180 * time.Second, want: "at least 32 bytes"},
		{name: "blank issuer", secret: testSigningSecret, issuer: "   ", audience: "maintenance-api", ttl: 180 * time.Second, want: "issuer"},
		{name: "blank audience", secret: testSigningSecret, issuer: "weknora", audience: "\t", ttl: 180 * time.Second, want: "audience"},
		{name: "zero ttl", secret: testSigningSecret, issuer: "weknora", audience: "maintenance-api", ttl: 0, want: "exactly 180 seconds"},
		{name: "short ttl", secret: testSigningSecret, issuer: "weknora", audience: "maintenance-api", ttl: 179 * time.Second, want: "exactly 180 seconds"},
		{name: "long ttl", secret: testSigningSecret, issuer: "weknora", audience: "maintenance-api", ttl: 181 * time.Second, want: "exactly 180 seconds"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := NewSigner([]byte(tt.secret), tt.issuer, tt.audience, tt.ttl)
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("NewSigner() error = %v, want containing %q", err, tt.want)
			}
		})
	}
}

func TestSignerRejectsIncompleteOrInvalidActor(t *testing.T) {
	signer, err := NewSigner([]byte(testSigningSecret), "weknora", "maintenance-api", 180*time.Second)
	if err != nil {
		t.Fatalf("NewSigner() error = %v", err)
	}

	valid := Actor{UserID: "u-1", TenantID: "t-1", Roles: []string{"viewer"}, RequestID: "r-1"}
	tests := []struct {
		name  string
		actor Actor
		want  string
	}{
		{name: "missing user", actor: Actor{TenantID: valid.TenantID, Roles: valid.Roles, RequestID: valid.RequestID}, want: "user_id"},
		{name: "blank tenant", actor: Actor{UserID: valid.UserID, TenantID: "  ", Roles: valid.Roles, RequestID: valid.RequestID}, want: "tenant_id"},
		{name: "missing request", actor: Actor{UserID: valid.UserID, TenantID: valid.TenantID, Roles: valid.Roles}, want: "request_id"},
		{name: "missing roles", actor: Actor{UserID: valid.UserID, TenantID: valid.TenantID, RequestID: valid.RequestID}, want: "role"},
		{name: "blank role", actor: Actor{UserID: valid.UserID, TenantID: valid.TenantID, Roles: []string{"viewer", " "}, RequestID: valid.RequestID}, want: "role"},
		{name: "unknown role", actor: Actor{UserID: valid.UserID, TenantID: valid.TenantID, Roles: []string{"owner"}, RequestID: valid.RequestID}, want: "unsupported maintenance role"},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			_, err := signer.Sign(tt.actor)
			if err == nil || !strings.Contains(err.Error(), tt.want) {
				t.Fatalf("Sign() error = %v, want containing %q", err, tt.want)
			}
		})
	}
}

func TestSignerCopiesSecretAndGeneratesUniqueTokenIDs(t *testing.T) {
	secret := []byte(testSigningSecret)
	signer, err := NewSigner(secret, "weknora", "maintenance-api", 180*time.Second)
	if err != nil {
		t.Fatalf("NewSigner() error = %v", err)
	}
	for i := range secret {
		secret[i] = 'x'
	}

	now := time.Unix(1_784_894_400, 0).UTC()
	signer.now = func() time.Time { return now }
	actor := Actor{UserID: "u-1", TenantID: "t-1", Roles: []string{"admin"}, RequestID: "r-1"}

	first, err := signer.Sign(actor)
	if err != nil {
		t.Fatalf("first Sign() error = %v", err)
	}
	second, err := signer.Sign(actor)
	if err != nil {
		t.Fatalf("second Sign() error = %v", err)
	}
	if first == second {
		t.Fatal("two tokens signed at the same instant must have distinct jti values")
	}

	for _, tokenString := range []string{first, second} {
		parsed, err := jwt.ParseWithClaims(tokenString, &Claims{}, func(token *jwt.Token) (any, error) {
			return []byte(testSigningSecret), nil
		}, jwt.WithValidMethods([]string{"HS256"}), jwt.WithAudience("maintenance-api"), jwt.WithIssuer("weknora"), jwt.WithTimeFunc(func() time.Time { return now }))
		if err != nil || !parsed.Valid {
			t.Fatalf("token signed after caller secret mutation is invalid: parsed=%v err=%v", parsed, err)
		}
	}
}
