package containerwiringcontract_test

import (
	"go/ast"
	"go/parser"
	"go/token"
	"os"
	"path/filepath"
	"runtime"
	"testing"
)

func TestContainerRegistersUnifiedMaintenanceRuntimeGraph(t *testing.T) {
	containerFile := containerSourcePath(t)
	source, err := os.ReadFile(containerFile)
	if err != nil {
		t.Fatalf("read container.go: %v", err)
	}

	fset := token.NewFileSet()
	file, err := parser.ParseFile(
		fset,
		containerFile,
		source,
		parser.SkipObjectResolution,
	)
	if err != nil {
		t.Fatalf("parse container.go: %v", err)
	}

	if !hasImportPath(
		file,
		"github.com/Tencent/WeKnora/internal/maintenanceintegration",
	) {
		t.Fatal("container.go does not import maintenanceintegration")
	}

	required := []string{
		"maintenanceintegration.NewRuntime",
		"maintenanceintegration.ProxyFromRuntime",
		"maintenanceintegration.FinalizerFromRuntime",
		"session.NewHandler",
	}
	for _, provider := range required {
		if !hasProvideCall(file, provider) {
			t.Fatalf(
				"container.go does not register provider %s",
				provider,
			)
		}
	}

	if hasProvideCall(file, "newMaintenanceProxy") {
		t.Fatal(
			"container.go still registers legacy newMaintenanceProxy; " +
				"proxy and exact-turn client must share Runtime signer",
		)
	}
}

func containerSourcePath(t *testing.T) string {
	t.Helper()

	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller(0) failed")
	}

	return filepath.Clean(filepath.Join(
		filepath.Dir(currentFile),
		"..",
		"container",
		"container.go",
	))
}

func hasImportPath(file *ast.File, want string) bool {
	for _, spec := range file.Imports {
		if spec.Path == nil {
			continue
		}
		if len(spec.Path.Value) >= 2 &&
			spec.Path.Value[1:len(spec.Path.Value)-1] == want {
			return true
		}
	}
	return false
}

func hasProvideCall(file *ast.File, wantProvider string) bool {
	found := false
	ast.Inspect(file, func(node ast.Node) bool {
		call, ok := node.(*ast.CallExpr)
		if !ok {
			return true
		}

		selector, ok := call.Fun.(*ast.SelectorExpr)
		if !ok || selector.Sel.Name != "Provide" || len(call.Args) == 0 {
			return true
		}

		if expressionName(call.Args[0]) == wantProvider {
			found = true
			return false
		}
		return true
	})
	return found
}

func expressionName(expr ast.Expr) string {
	switch value := expr.(type) {
	case *ast.Ident:
		return value.Name
	case *ast.SelectorExpr:
		prefix := expressionName(value.X)
		if prefix == "" {
			return value.Sel.Name
		}
		return prefix + "." + value.Sel.Name
	default:
		return ""
	}
}
