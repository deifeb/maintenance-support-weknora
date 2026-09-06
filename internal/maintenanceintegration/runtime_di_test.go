package maintenanceintegration

import (
	"testing"

	"github.com/Tencent/WeKnora/internal/maintenanceclient"
	"github.com/Tencent/WeKnora/internal/maintenanceprojection"
	"github.com/Tencent/WeKnora/internal/maintenanceproxy"
)

func TestRuntimeDIExtractorsPreserveExactInstances(t *testing.T) {
	proxy := &maintenanceproxy.Proxy{}
	client := &maintenanceclient.Client{}
	finalizer := maintenanceprojection.NewTerminalFinalizer(nil, nil)
	runtime := &Runtime{
		Proxy:     proxy,
		Client:    client,
		Finalizer: finalizer,
	}

	if got := ProxyFromRuntime(runtime); got != proxy {
		t.Fatalf("ProxyFromRuntime() = %p, want %p", got, proxy)
	}
	if got := FinalizerFromRuntime(runtime); got != finalizer {
		t.Fatalf("FinalizerFromRuntime() = %p, want %p", got, finalizer)
	}
}

func TestRuntimeDIExtractorsAreNilSafe(t *testing.T) {
	if got := ProxyFromRuntime(nil); got != nil {
		t.Fatalf("ProxyFromRuntime(nil) = %p, want nil", got)
	}
	if got := FinalizerFromRuntime(nil); got != nil {
		t.Fatalf("FinalizerFromRuntime(nil) = %p, want nil", got)
	}
}
