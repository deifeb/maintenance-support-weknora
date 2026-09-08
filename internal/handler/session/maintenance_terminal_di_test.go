package session

import (
	"reflect"
	"testing"

	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
)

func TestNewHandlerUsesConcreteTerminalFinalizerDependencyForDI(t *testing.T) {
	constructorType := reflect.TypeOf(NewHandler)
	if constructorType.NumIn() != 17 {
		t.Fatalf(
			"NewHandler input count = %d, want 17",
			constructorType.NumIn(),
		)
	}

	got := constructorType.In(16)
	want := reflect.TypeOf((*maintenanceprojection.TerminalFinalizer)(nil))
	if got != want {
		t.Fatalf(
			"NewHandler terminal dependency type = %v, want %v",
			got,
			want,
		)
	}
}
