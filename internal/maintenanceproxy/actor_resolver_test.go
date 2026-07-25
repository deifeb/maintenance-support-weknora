package maintenanceproxy

import (
	"context"
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
