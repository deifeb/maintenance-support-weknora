package session

import (
	"context"

	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
)

type terminalProjectionFinalizer interface {
	Finalize(
		ctx context.Context,
		actor maintenanceproxy.Actor,
		message *types.Message,
		reason maintenanceprojection.TerminalReason,
	) (maintenanceprojection.TerminalFinalizeResult, error)
}

func (h *Handler) finalizeAssistantTerminal(
	ctx context.Context,
	message *types.Message,
	reason maintenanceprojection.TerminalReason,
) (maintenanceprojection.TerminalFinalizeResult, error) {
	actor := maintenanceproxy.Actor{}

	if reason == maintenanceprojection.TerminalReasonNormal &&
		message != nil &&
		message.ExecutionContext.MaintenanceProjection != nil {
		if resolved, err := maintenanceproxy.ResolveWebActorContext(ctx); err == nil {
			actor = resolved
		}
	}

	return h.maintenanceTerminalFinalizer.Finalize(
		ctx,
		actor,
		message,
		reason,
	)
}
