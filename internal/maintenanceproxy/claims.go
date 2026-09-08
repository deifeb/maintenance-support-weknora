package maintenanceproxy

import "github.com/golang-jwt/jwt/v5"

// Actor is the authenticated WeKnora identity projected into the maintenance
// authorization model. It is resolved server-side and must never be populated
// from browser-controlled tenant or role fields.
type Actor struct {
	UserID    string
	TenantID  string
	Roles     []string
	RequestID string
}

// Claims is the short-lived identity envelope accepted by the private
// Maintenance API. RegisteredClaims supplies sub, iss, aud, iat, exp, and jti.
type Claims struct {
	TenantID  string   `json:"tenant_id"`
	Roles     []string `json:"roles"`
	RequestID string   `json:"request_id"`
	jwt.RegisteredClaims
}
