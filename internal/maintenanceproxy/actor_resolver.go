package maintenanceproxy

import (
	"context"
	"errors"
	"fmt"
	"strconv"
	"strings"

	"github.com/gin-gonic/gin"

	"github.com/Tencent/WeKnora/internal/types"
)

var errMaintenanceActorUnavailable = errors.New("maintenance actor unavailable")

func actorUnavailable(reason string) error {
	return fmt.Errorf("%w: %s", errMaintenanceActorUnavailable, reason)
}

// ResolveWebActor projects the explicit authenticated WeKnora web-user context
// into the actor contract used by the private Maintenance proxy.
func ResolveWebActor(c *gin.Context) (Actor, error) {
	if c == nil || c.Request == nil {
		return Actor{}, actorUnavailable("request context is missing")
	}
	return ResolveWebActorContext(c.Request.Context())
}

// ResolveWebActorContext projects the authenticated request context into the
// actor contract used by async Maintenance terminal finalization.
func ResolveWebActorContext(ctx context.Context) (Actor, error) {
	actor := Actor{}
	if ctx == nil {
		return actor, actorUnavailable("request context is missing")
	}

	requestID, ok := ctx.Value(types.RequestIDContextKey).(string)
	if !ok || strings.TrimSpace(requestID) == "" {
		return actor, actorUnavailable("request id is missing")
	}
	actor.RequestID = requestID

	principal, ok := ctx.Value(types.PrincipalContextKey).(types.Principal)
	if !ok || !principal.Valid() {
		return actor, actorUnavailable("principal is missing or invalid")
	}
	if principal.Type != types.PrincipalWebUser {
		return actor, actorUnavailable("principal type is not web_user")
	}

	userID, ok := ctx.Value(types.UserIDContextKey).(string)
	if !ok || strings.TrimSpace(userID) == "" {
		return actor, actorUnavailable("user id is missing")
	}
	if principal.ID != userID {
		return actor, actorUnavailable("principal and user id do not match")
	}

	tenantID, ok := ctx.Value(types.TenantIDContextKey).(uint64)
	if !ok || tenantID == 0 {
		return actor, actorUnavailable("tenant id is missing or invalid")
	}

	tenantRole, ok := ctx.Value(types.TenantRoleContextKey).(types.TenantRole)
	if !ok || !tenantRole.IsValid() {
		return actor, actorUnavailable("tenant role is missing or invalid")
	}

	systemAdmin := false
	if raw := ctx.Value(types.SystemAdminContextKey); raw != nil {
		value, valid := raw.(bool)
		if !valid {
			return actor, actorUnavailable("system admin flag is invalid")
		}
		systemAdmin = value
	}

	role, err := mapMaintenanceRole(tenantRole, systemAdmin)
	if err != nil {
		return actor, err
	}

	actor.UserID = userID
	actor.TenantID = strconv.FormatUint(tenantID, 10)
	actor.Roles = []string{role}
	return actor, nil
}

func mapMaintenanceRole(tenantRole types.TenantRole, systemAdmin bool) (string, error) {
	if systemAdmin {
		return "admin", nil
	}

	switch tenantRole {
	case types.TenantRoleOwner, types.TenantRoleAdmin:
		return "admin", nil
	case types.TenantRoleContributor:
		return "contributor", nil
	case types.TenantRoleViewer:
		return "viewer", nil
	default:
		return "", actorUnavailable("tenant role is unsupported")
	}
}
