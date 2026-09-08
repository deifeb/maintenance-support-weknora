package maintenanceproxy

import (
	"context"
	"errors"
	"net/http"
	"net/http/httptest"
	"reflect"
	"testing"

	"github.com/gin-gonic/gin"

	"github.com/Tencent/WeKnora/internal/types"
)

func newActorTestContext(
	principal types.Principal,
	userID string,
	tenantID uint64,
	role types.TenantRole,
	systemAdmin *bool,
	requestID string,
) *gin.Context {
	recorder := httptest.NewRecorder()
	ginContext, _ := gin.CreateTestContext(recorder)
	request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs", nil)

	ctx := request.Context()
	ctx = context.WithValue(ctx, types.PrincipalContextKey, principal)
	ctx = context.WithValue(ctx, types.UserIDContextKey, userID)
	ctx = context.WithValue(ctx, types.TenantIDContextKey, tenantID)
	ctx = context.WithValue(ctx, types.TenantRoleContextKey, role)
	ctx = context.WithValue(ctx, types.RequestIDContextKey, requestID)
	if systemAdmin != nil {
		ctx = context.WithValue(ctx, types.SystemAdminContextKey, *systemAdmin)
	}

	ginContext.Request = request.WithContext(ctx)
	return ginContext
}

func newActorTestContextFromValues(values map[types.ContextKey]any) *gin.Context {
	recorder := httptest.NewRecorder()
	ginContext, _ := gin.CreateTestContext(recorder)
	request := httptest.NewRequest(http.MethodGet, "/api/maintenance/jobs", nil)
	ctx := request.Context()
	for key, value := range values {
		ctx = context.WithValue(ctx, key, value)
	}
	ginContext.Request = request.WithContext(ctx)
	return ginContext
}

func validActorContextValues() map[types.ContextKey]any {
	return map[types.ContextKey]any{
		types.RequestIDContextKey:   "req-valid",
		types.PrincipalContextKey:   types.Principal{Type: types.PrincipalWebUser, ID: "user-1"},
		types.UserIDContextKey:      "user-1",
		types.TenantIDContextKey:    uint64(12),
		types.TenantRoleContextKey:  types.TenantRoleContributor,
		types.SystemAdminContextKey: false,
	}
}

func cloneActorContextValues(source map[types.ContextKey]any) map[types.ContextKey]any {
	cloned := make(map[types.ContextKey]any, len(source))
	for key, value := range source {
		cloned[key] = value
	}
	return cloned
}

func boolPointer(value bool) *bool {
	return &value
}

func TestResolveWebActorMapsRoles(t *testing.T) {
	tests := []struct {
		name        string
		role        types.TenantRole
		systemAdmin *bool
		expected    string
	}{
		{name: "viewer", role: types.TenantRoleViewer, systemAdmin: boolPointer(false), expected: "viewer"},
		{name: "contributor", role: types.TenantRoleContributor, systemAdmin: boolPointer(false), expected: "contributor"},
		{name: "admin", role: types.TenantRoleAdmin, systemAdmin: boolPointer(false), expected: "admin"},
		{name: "owner", role: types.TenantRoleOwner, systemAdmin: boolPointer(false), expected: "admin"},
		{name: "missing system admin flag", role: types.TenantRoleViewer, systemAdmin: nil, expected: "viewer"},
		{name: "system admin elevation", role: types.TenantRoleViewer, systemAdmin: boolPointer(true), expected: "admin"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			principal := types.Principal{Type: types.PrincipalWebUser, ID: "user-1"}
			ginContext := newActorTestContext(principal, "user-1", 12, test.role, test.systemAdmin, "req-1")

			actor, err := ResolveWebActor(ginContext)
			if err != nil {
				t.Fatalf("ResolveWebActor() error = %v", err)
			}

			expectedRoles := []string{test.expected}
			if actor.UserID != "user-1" {
				t.Fatalf("UserID = %q, want user-1", actor.UserID)
			}
			if actor.TenantID != "12" {
				t.Fatalf("TenantID = %q, want 12", actor.TenantID)
			}
			if actor.RequestID != "req-1" {
				t.Fatalf("RequestID = %q, want req-1", actor.RequestID)
			}
			if !reflect.DeepEqual(actor.Roles, expectedRoles) {
				t.Fatalf("Roles = %#v, want %#v", actor.Roles, expectedRoles)
			}
		})
	}
}

func TestResolveWebActorRejectsInvalidPrincipal(t *testing.T) {
	tests := []struct {
		name      string
		principal any
		userID    any
	}{
		{name: "missing principal", principal: nil, userID: "user-1"},
		{name: "wrong principal value type", principal: "web_user:user-1", userID: "user-1"},
		{name: "principal pointer is not trusted context type", principal: &types.Principal{Type: types.PrincipalWebUser, ID: "user-1"}, userID: "user-1"},
		{name: "blank principal", principal: types.Principal{}, userID: "user-1"},
		{name: "tenant api key", principal: types.Principal{Type: types.PrincipalAPITenant, ID: "12:1"}, userID: "system-12"},
		{name: "platform api key", principal: types.Principal{Type: types.PrincipalAPIPlatform, ID: "key-1"}, userID: "system-12"},
		{name: "external api user", principal: types.Principal{Type: types.PrincipalAPIExternalUser, ID: "external-1"}, userID: "external-1"},
		{name: "im user", principal: types.Principal{Type: types.PrincipalIMUser, ID: "im-1"}, userID: "user-1"},
		{name: "embed channel", principal: types.Principal{Type: types.PrincipalEmbedChannel, ID: "channel-1"}, userID: "user-1"},
		{name: "embed session", principal: types.Principal{Type: types.PrincipalEmbedSession, ID: "session-1"}, userID: "user-1"},
		{name: "embed visitor", principal: types.Principal{Type: types.PrincipalEmbedVisitor, ID: "visitor-1"}, userID: "user-1"},
		{name: "mismatched web user", principal: types.Principal{Type: types.PrincipalWebUser, ID: "user-2"}, userID: "user-1"},
	}

	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			values := validActorContextValues()
			if test.principal == nil {
				delete(values, types.PrincipalContextKey)
			} else {
				values[types.PrincipalContextKey] = test.principal
			}
			if test.userID == nil {
				delete(values, types.UserIDContextKey)
			} else {
				values[types.UserIDContextKey] = test.userID
			}

			actor, err := ResolveWebActor(newActorTestContextFromValues(values))
			if !errors.Is(err, errMaintenanceActorUnavailable) {
				t.Fatalf("error = %v, want errMaintenanceActorUnavailable", err)
			}
			if actor.RequestID != "req-valid" {
				t.Fatalf("RequestID = %q, want req-valid", actor.RequestID)
			}
		})
	}
}

func TestResolveWebActorRejectsIncompleteIdentity(t *testing.T) {
	actor, err := ResolveWebActor(nil)
	if !errors.Is(err, errMaintenanceActorUnavailable) {
		t.Fatalf("nil context error = %v, want errMaintenanceActorUnavailable", err)
	}
	if !reflect.DeepEqual(actor, Actor{}) {
		t.Fatalf("nil context actor = %#v, want empty Actor", actor)
	}

	recorder := httptest.NewRecorder()
	ginContext, _ := gin.CreateTestContext(recorder)
	actor, err = ResolveWebActor(ginContext)
	if !errors.Is(err, errMaintenanceActorUnavailable) {
		t.Fatalf("nil request error = %v, want errMaintenanceActorUnavailable", err)
	}
	if !reflect.DeepEqual(actor, Actor{}) {
		t.Fatalf("nil request actor = %#v, want empty Actor", actor)
	}

	tests := []struct {
		name              string
		mutate            func(map[types.ContextKey]any)
		expectedRequestID string
	}{
		{name: "missing request id", mutate: func(values map[types.ContextKey]any) { delete(values, types.RequestIDContextKey) }},
		{name: "request id wrong type", mutate: func(values map[types.ContextKey]any) { values[types.RequestIDContextKey] = 42 }},
		{name: "blank request id", mutate: func(values map[types.ContextKey]any) { values[types.RequestIDContextKey] = "   " }},
		{name: "missing user id", mutate: func(values map[types.ContextKey]any) { delete(values, types.UserIDContextKey) }, expectedRequestID: "req-valid"},
		{name: "user id wrong type", mutate: func(values map[types.ContextKey]any) { values[types.UserIDContextKey] = 42 }, expectedRequestID: "req-valid"},
		{name: "blank user id", mutate: func(values map[types.ContextKey]any) { values[types.UserIDContextKey] = "   " }, expectedRequestID: "req-valid"},
		{name: "missing tenant id", mutate: func(values map[types.ContextKey]any) { delete(values, types.TenantIDContextKey) }, expectedRequestID: "req-valid"},
		{name: "tenant id wrong type", mutate: func(values map[types.ContextKey]any) { values[types.TenantIDContextKey] = "12" }, expectedRequestID: "req-valid"},
		{name: "zero tenant id", mutate: func(values map[types.ContextKey]any) { values[types.TenantIDContextKey] = uint64(0) }, expectedRequestID: "req-valid"},
		{name: "missing tenant role", mutate: func(values map[types.ContextKey]any) { delete(values, types.TenantRoleContextKey) }, expectedRequestID: "req-valid"},
		{name: "tenant role wrong type", mutate: func(values map[types.ContextKey]any) { values[types.TenantRoleContextKey] = "viewer" }, expectedRequestID: "req-valid"},
		{name: "unsupported tenant role", mutate: func(values map[types.ContextKey]any) { values[types.TenantRoleContextKey] = types.TenantRole("operator") }, expectedRequestID: "req-valid"},
		{name: "system admin wrong type", mutate: func(values map[types.ContextKey]any) { values[types.SystemAdminContextKey] = "true" }, expectedRequestID: "req-valid"},
	}

	base := validActorContextValues()
	for _, test := range tests {
		t.Run(test.name, func(t *testing.T) {
			values := cloneActorContextValues(base)
			test.mutate(values)

			actor, err := ResolveWebActor(newActorTestContextFromValues(values))
			if !errors.Is(err, errMaintenanceActorUnavailable) {
				t.Fatalf("error = %v, want errMaintenanceActorUnavailable", err)
			}
			if actor.RequestID != test.expectedRequestID {
				t.Fatalf("RequestID = %q, want %q", actor.RequestID, test.expectedRequestID)
			}
		})
	}
}

func TestResolveWebActorIgnoresBrowserIdentityHeaders(t *testing.T) {
	principal := types.Principal{Type: types.PrincipalWebUser, ID: "user-1"}
	ginContext := newActorTestContext(principal, "user-1", 12, types.TenantRoleViewer, boolPointer(false), "req-spoof")
	ginContext.Request.Header.Set("X-Tenant-ID", "999")
	ginContext.Request.Header.Set("X-User-ID", "attacker")
	ginContext.Request.Header.Set("X-Role", "admin")
	ginContext.Request.Header.Set("X-User-Roles", "admin")
	ginContext.Request.Header.Set("X-System-Admin", "true")

	actor, err := ResolveWebActor(ginContext)
	if err != nil {
		t.Fatalf("ResolveWebActor() error = %v", err)
	}
	if actor.UserID != "user-1" || actor.TenantID != "12" || actor.RequestID != "req-spoof" {
		t.Fatalf("actor = %#v", actor)
	}
	if !reflect.DeepEqual(actor.Roles, []string{"viewer"}) {
		t.Fatalf("Roles = %#v, want viewer", actor.Roles)
	}
}

func TestMapMaintenanceRoleRejectsUnsupportedRole(t *testing.T) {
	role, err := mapMaintenanceRole(types.TenantRole("operator"), false)
	if !errors.Is(err, errMaintenanceActorUnavailable) {
		t.Fatalf("error = %v, want errMaintenanceActorUnavailable", err)
	}
	if role != "" {
		t.Fatalf("role = %q, want empty", role)
	}
}
