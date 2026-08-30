package maintenanceproxy

import (
	"context"
	"errors"
	"reflect"
	"testing"

	"github.com/Tencent/WeKnora/internal/types"
)

func actorContextForAsyncTerminal() context.Context {
	ctx := context.Background()
	ctx = context.WithValue(
		ctx,
		types.RequestIDContextKey,
		"req-terminal-1",
	)
	ctx = context.WithValue(
		ctx,
		types.PrincipalContextKey,
		types.Principal{
			Type: types.PrincipalWebUser,
			ID:   "user-1",
		},
	)
	ctx = context.WithValue(
		ctx,
		types.UserIDContextKey,
		"user-1",
	)
	ctx = context.WithValue(
		ctx,
		types.TenantIDContextKey,
		uint64(12),
	)
	ctx = context.WithValue(
		ctx,
		types.TenantRoleContextKey,
		types.TenantRoleContributor,
	)
	ctx = context.WithValue(
		ctx,
		types.SystemAdminContextKey,
		false,
	)
	return ctx
}

func TestResolveWebActorContextSupportsAsyncTerminalFinalization(
	t *testing.T,
) {
	actor, err := ResolveWebActorContext(
		actorContextForAsyncTerminal(),
	)
	if err != nil {
		t.Fatalf("ResolveWebActorContext() error = %v", err)
	}

	expected := Actor{
		UserID:    "user-1",
		TenantID:  "12",
		Roles:     []string{"contributor"},
		RequestID: "req-terminal-1",
	}
	if !reflect.DeepEqual(actor, expected) {
		t.Fatalf(
			"ResolveWebActorContext() = %#v, want %#v",
			actor,
			expected,
		)
	}
}

func TestResolveWebActorContextFailsClosedWithoutExactIdentity(
	t *testing.T,
) {
	ctx := actorContextForAsyncTerminal()
	ctx = context.WithValue(
		ctx,
		types.PrincipalContextKey,
		types.Principal{
			Type: types.PrincipalWebUser,
			ID:   "other-user",
		},
	)

	actor, err := ResolveWebActorContext(ctx)
	if !errors.Is(err, errMaintenanceActorUnavailable) {
		t.Fatalf(
			"error = %v, want errMaintenanceActorUnavailable",
			err,
		)
	}
	if !reflect.DeepEqual(actor, Actor{
		RequestID: "req-terminal-1",
	}) {
		t.Fatalf(
			"actor = %#v, want request-id-only fail-closed actor",
			actor,
		)
	}
}
