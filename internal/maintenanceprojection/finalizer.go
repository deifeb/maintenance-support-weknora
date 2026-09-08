package maintenanceprojection

import (
	"context"
	"errors"

	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
	"github.com/Tencent/WeKnora/internal/types"
)

// TerminalReason identifies why an assistant turn is being finalized.
type TerminalReason string

const (
	TerminalReasonNormal TerminalReason = "normal"
	TerminalReasonStop   TerminalReason = "stop"
	TerminalReasonError  TerminalReason = "error"
)

// TerminalProjectionClient resolves the validated card snapshot for one exact
// persisted Maintenance AI trigger turn.
type TerminalProjectionClient interface {
	RecoverExactTurn(
		ctx context.Context,
		actor maintenanceproxy.Actor,
		source types.MaintenanceProjectionProvenance,
	) (types.MaintenanceCards, error)
}

// TerminalMessageStore is the durable race arbiter for assistant completion.
// The implementation must update only an open assistant row and report false
// when another terminal path has already finalized that same message.
type TerminalMessageStore interface {
	FinalizeAssistantMessageIfOpen(
		ctx context.Context,
		message *types.Message,
	) (bool, error)
}

// TerminalFinalizeResult reports durable finalization separately from the
// auxiliary Maintenance projection outcome.
type TerminalFinalizeResult struct {
	Persisted       bool
	ProjectionError error
}

// TerminalFinalizer coordinates projection and one conditional terminal write.
type TerminalFinalizer struct {
	client TerminalProjectionClient
	store  TerminalMessageStore
}

// NewTerminalFinalizer creates the terminal projection coordinator.
func NewTerminalFinalizer(
	client TerminalProjectionClient,
	store TerminalMessageStore,
) *TerminalFinalizer {
	return &TerminalFinalizer{
		client: client,
		store:  store,
	}
}

// Finalize completes one assistant message. Stop finalization never starts a
// Maintenance projection. Normal projection failures fail closed while the
// assistant text still completes.
func (f *TerminalFinalizer) Finalize(
	ctx context.Context,
	actor maintenanceproxy.Actor,
	message *types.Message,
	reason TerminalReason,
) (TerminalFinalizeResult, error) {
	var result TerminalFinalizeResult

	if f == nil {
		return result, errors.New("maintenance terminal finalizer is nil")
	}
	if f.store == nil {
		return result, errors.New("maintenance terminal message store is nil")
	}
	if message == nil {
		return result, errors.New("assistant message is nil")
	}
	if message.IsCompleted {
		return result, nil
	}
	if reason != TerminalReasonNormal &&
		reason != TerminalReasonStop &&
		reason != TerminalReasonError {
		return result, errors.New("unsupported terminal finalization reason")
	}

	staged := cloneMessageForTerminalFinalize(message)
	staged.IsCompleted = true

	switch reason {
	case TerminalReasonStop, TerminalReasonError:
		staged.MaintenanceCards = make(types.MaintenanceCards, 0)

	case TerminalReasonNormal:
		source := staged.ExecutionContext.MaintenanceProjection
		if source != nil {
			if f.client == nil {
				result.ProjectionError = errors.New(
					"maintenance projection client is nil",
				)
				staged.MaintenanceCards = make(types.MaintenanceCards, 0)
			} else {
				cards, err := f.client.RecoverExactTurn(
					ctx,
					actor,
					*source,
				)
				if err != nil {
					result.ProjectionError = err
					staged.MaintenanceCards = make(
						types.MaintenanceCards,
						0,
					)
				} else {
					staged.MaintenanceCards = append(
						types.MaintenanceCards(nil),
						cards...,
					)
				}
			}
		}
	}

	persisted, err := f.store.FinalizeAssistantMessageIfOpen(
		ctx,
		staged,
	)
	if err != nil {
		return result, err
	}
	if !persisted {
		return result, nil
	}

	message.IsCompleted = staged.IsCompleted
	message.MaintenanceCards = append(
		types.MaintenanceCards(nil),
		staged.MaintenanceCards...,
	)
	result.Persisted = true
	return result, nil
}

func cloneMessageForTerminalFinalize(message *types.Message) *types.Message {
	cloned := *message
	cloned.MaintenanceCards = append(
		types.MaintenanceCards(nil),
		message.MaintenanceCards...,
	)
	return &cloned
}
