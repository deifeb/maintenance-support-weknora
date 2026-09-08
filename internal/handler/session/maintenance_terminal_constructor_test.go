package session

import (
	"testing"

	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
)

func TestNewHandlerInjectsMaintenanceTerminalFinalizer(t *testing.T) {
	finalizer := maintenanceprojection.NewTerminalFinalizer(nil, nil)

	handler := NewHandler(
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		nil,
		finalizer,
	)

	if handler == nil {
		t.Fatal("NewHandler() = nil")
	}
	if handler.maintenanceTerminalFinalizer != finalizer {
		t.Fatal("NewHandler() did not retain the runtime terminal finalizer")
	}
}
