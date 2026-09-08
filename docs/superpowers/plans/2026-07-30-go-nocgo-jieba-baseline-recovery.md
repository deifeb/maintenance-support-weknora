# Go Non-cgo Jieba Baseline Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow Windows and other `CGO_ENABLED=0` builds to compile the WeKnora packages that depend on Chinese search tokenization while retaining jieba behavior in cgo builds.

**Architecture:** Replace the exported concrete `*gojieba.Jieba` global with the smallest interface used by callers. Construct the real dictionary-aware jieba tokenizer in a cgo-tagged file and provide a deterministic pure-Go search-token fallback in a non-cgo file.

**Tech Stack:** Go 1.26, build constraints, `gojieba`, Unicode tokenization, Go tests.

## Global Constraints

- cgo builds retain the existing `gojieba.NewJieba` construction and `JIEBA_DICT_DIR` custom dictionary behavior.
- Existing callers continue using `types.Jieba.CutForSearch(text, true)` without conditional compilation.
- The non-cgo fallback is deterministic, has no external files, never panics on empty or Unicode input, and returns useful multi-rune tokens.
- This compile-baseline fix does not change Maintenance routes, identity, tenant, RBAC, or business contracts.

---

### Task 1: Introduce Build-Specific Search Tokenizers

**Files:**
- Modify: `internal/types/evaluation.go`
- Create: `internal/types/jieba_cgo.go`
- Create: `internal/types/jieba_nocgo.go`
- Create: `internal/types/jieba_nocgo_test.go`

**Interfaces:**
- Produces: an internal `searchTokenizer` interface with `CutForSearch(string, bool) []string` and the unchanged exported `types.Jieba` value.
- Consumed by: search utilities plus Qdrant and Weaviate query tokenization.

- [ ] **Step 1: Write the failing non-cgo test**

With `//go:build !cgo`, assert empty input returns no tokens; `"航空发动机 maintenance"` yields the complete Han run, overlapping two-rune Han search tokens, and `maintenance`; repeated calls return identical slices.

- [ ] **Step 2: Run and verify RED**

```powershell
$env:CGO_ENABLED = '0'
go test ./internal/types -run TestNonCGOJiebaFallback -count=1
```

Expected: build failure because `evaluation.go` references cgo-only `gojieba.Jieba/NewJieba`.

- [ ] **Step 3: Split construction by build constraint**

In `evaluation.go` declare:

```go
type searchTokenizer interface {
	CutForSearch(string, bool) []string
}

var Jieba searchTokenizer = newSearchTokenizer()
```

In `jieba_cgo.go`, move the current `JIEBA_DICT_DIR` and five dictionary paths unchanged into `newSearchTokenizer() searchTokenizer` returning `gojieba.NewJieba(...)`.

In `jieba_nocgo.go`, split input into Unicode letter/number runs. Emit non-Han runs once. For each Han run with two or more runes, emit the whole run once and then each unique overlapping two-rune token in source order. Ignore punctuation/whitespace and return an empty slice for empty input.

- [ ] **Step 4: Run focused and affected gates**

```powershell
$env:CGO_ENABLED = '0'
go test ./internal/types -run TestNonCGOJiebaFallback -count=1
go test ./internal/searchutil
go test ./internal/maintenanceproxy ./internal/router
```

Expected: all commands exit 0, or the final gate exposes a separately identified dependency blocker with this task's errors absent.

- [ ] **Step 5: Commit**

```powershell
git add internal/types/evaluation.go internal/types/jieba_cgo.go internal/types/jieba_nocgo.go internal/types/jieba_nocgo_test.go
git commit -m "fix: provide non-cgo search tokenization"
```
