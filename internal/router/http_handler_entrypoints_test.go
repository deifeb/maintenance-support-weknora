package router

import (
	"os"
	"path/filepath"
	"runtime"
	"strings"
	"testing"
)

func readApplicationHandlerRepoFile(t *testing.T, relativePath string) string {
	t.Helper()

	_, currentFile, _, ok := runtime.Caller(0)
	if !ok {
		t.Fatal("resolve current test file")
	}
	repoRoot := filepath.Clean(filepath.Join(filepath.Dir(currentFile), "..", ".."))
	content, err := os.ReadFile(filepath.Join(repoRoot, filepath.FromSlash(relativePath)))
	if err != nil {
		t.Fatalf("read %s: %v", relativePath, err)
	}
	return string(content)
}

func TestApplicationHandlerProviderRegistration(t *testing.T) {
	source := readApplicationHandlerRepoFile(t, "internal/container/container.go")

	routerIndex := strings.Index(source, "must(container.Provide(router.NewRouter))")
	if routerIndex < 0 {
		t.Fatal("router.NewRouter provider registration is missing")
	}

	applicationHandlerIndex := strings.Index(source, "must(container.Provide(router.NewApplicationHandler))")
	if applicationHandlerIndex < 0 {
		t.Fatal("router.NewApplicationHandler provider registration is missing")
	}
	if applicationHandlerIndex <= routerIndex {
		t.Fatal("router.NewApplicationHandler must be provided after router.NewRouter")
	}
}

func TestEntrypointsUseApplicationHandler(t *testing.T) {
	for _, entrypoint := range []string{
		"cmd/server/main.go",
		"cmd/desktop/main.go",
	} {
		t.Run(entrypoint, func(t *testing.T) {
			source := readApplicationHandlerRepoFile(t, entrypoint)

			for _, required := range []string{
				`"github.com/Tencent/WeKnora/internal/router"`,
				"applicationHandler *router.ApplicationHandler",
				"Handler: applicationHandler",
			} {
				if !strings.Contains(source, required) {
					t.Fatalf("%s is missing %q", entrypoint, required)
				}
			}

			for _, forbidden := range []string{
				"router *gin.Engine",
				"Handler: router",
			} {
				if strings.Contains(source, forbidden) {
					t.Fatalf("%s must not contain %q", entrypoint, forbidden)
				}
			}
		})
	}
}
