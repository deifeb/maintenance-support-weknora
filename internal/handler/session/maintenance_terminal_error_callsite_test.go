package session

import (
	"go/ast"
	"go/parser"
	"go/token"
	"path/filepath"
	"runtime"
	"testing"
)

func TestExecuteQAServiceErrorUsesErrorTerminalFinalizerBeforeErrorEvent(
	t *testing.T,
) {
	_, thisFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("runtime.Caller failed")
	}
	qaPath := filepath.Join(filepath.Dir(thisFile), "qa.go")

	fset := token.NewFileSet()
	file, err := parser.ParseFile(fset, qaPath, nil, parser.AllErrors)
	if err != nil {
		t.Fatalf("parse qa.go: %v", err)
	}

	var executeQA *ast.FuncDecl
	for _, decl := range file.Decls {
		fn, ok := decl.(*ast.FuncDecl)
		if ok && fn.Name != nil && fn.Name.Name == "executeQA" {
			executeQA = fn
			break
		}
	}
	if executeQA == nil || executeQA.Body == nil {
		t.Fatal("executeQA function not found")
	}

	var serviceErrIf *ast.IfStmt
	ast.Inspect(executeQA.Body, func(node ast.Node) bool {
		if serviceErrIf != nil {
			return false
		}
		ifStmt, ok := node.(*ast.IfStmt)
		if !ok {
			return true
		}
		binary, ok := ifStmt.Cond.(*ast.BinaryExpr)
		if !ok || binary.Op != token.NEQ {
			return true
		}
		ident, ok := binary.X.(*ast.Ident)
		if !ok || ident.Name != "serviceErr" {
			return true
		}
		nilIdent, ok := binary.Y.(*ast.Ident)
		if !ok || nilIdent.Name != "nil" {
			return true
		}
		serviceErrIf = ifStmt
		return false
	})
	if serviceErrIf == nil {
		t.Fatal("executeQA serviceErr != nil branch not found")
	}

	var finalizePos token.Pos
	var errorEventPos token.Pos
	var hasErrorReason bool

	ast.Inspect(serviceErrIf.Body, func(node ast.Node) bool {
		call, ok := node.(*ast.CallExpr)
		if !ok {
			return true
		}

		if selector, ok := call.Fun.(*ast.SelectorExpr); ok {
			if selector.Sel.Name == "finalizeAssistantTerminal" {
				finalizePos = call.Pos()
				for _, arg := range call.Args {
					sel, ok := arg.(*ast.SelectorExpr)
					if !ok {
						continue
					}
					pkg, ok := sel.X.(*ast.Ident)
					if ok &&
						pkg.Name == "maintenanceprojection" &&
						sel.Sel.Name == "TerminalReasonError" {
						hasErrorReason = true
					}
				}
			}

			if selector.Sel.Name == "Emit" {
				for _, arg := range call.Args {
					composite, ok := arg.(*ast.CompositeLit)
					if !ok {
						continue
					}
					for _, elt := range composite.Elts {
						kv, ok := elt.(*ast.KeyValueExpr)
						if !ok {
							continue
						}
						key, ok := kv.Key.(*ast.Ident)
						if !ok || key.Name != "Type" {
							continue
						}
						sel, ok := kv.Value.(*ast.SelectorExpr)
						if !ok || sel.Sel.Name != "EventError" {
							continue
						}
						errorEventPos = call.Pos()
					}
				}
			}
		}
		return true
	})

	if finalizePos == token.NoPos {
		t.Fatal(
			"serviceErr branch does not call finalizeAssistantTerminal",
		)
	}
	if !hasErrorReason {
		t.Fatal(
			"serviceErr terminal finalizer does not use maintenanceprojection.TerminalReasonError",
		)
	}
	if errorEventPos == token.NoPos {
		t.Fatal("serviceErr branch does not emit EventError")
	}
	if finalizePos > errorEventPos {
		t.Fatal(
			"serviceErr terminal finalization must happen before emitting the terminal EventError",
		)
	}
}
