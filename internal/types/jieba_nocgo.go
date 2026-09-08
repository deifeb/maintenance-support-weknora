//go:build !cgo

package types

import "unicode"

type fallbackSearchTokenizer struct{}

type tokenRun struct {
	runes []rune
	isHan bool
}

func newSearchTokenizer() searchTokenizer {
	return fallbackSearchTokenizer{}
}

func (fallbackSearchTokenizer) Cut(text string, _ bool) []string {
	runs := splitTokenRuns(text)
	tokens := make([]string, 0, len(runs))
	for _, run := range runs {
		tokens = append(tokens, string(run.runes))
	}
	return tokens
}

func (fallbackSearchTokenizer) CutForSearch(text string, _ bool) []string {
	runs := splitTokenRuns(text)
	var tokens []string
	for _, run := range runs {
		tokens = append(tokens, string(run.runes))
		if !run.isHan || len(run.runes) < 2 {
			continue
		}

		seen := make(map[string]struct{}, len(run.runes)-1)
		for i := 0; i < len(run.runes)-1; i++ {
			token := string(run.runes[i : i+2])
			if _, ok := seen[token]; ok {
				continue
			}
			seen[token] = struct{}{}
			tokens = append(tokens, token)
		}
	}
	return tokens
}

func splitTokenRuns(text string) []tokenRun {
	var runs []tokenRun
	var run []rune
	var runIsHan bool

	emitRun := func() {
		if len(run) == 0 {
			return
		}
		runs = append(runs, tokenRun{runes: run, isHan: runIsHan})
		run = nil
	}

	for _, r := range text {
		if !unicode.IsLetter(r) && !unicode.IsNumber(r) {
			emitRun()
			continue
		}

		isHan := unicode.Is(unicode.Han, r)
		if len(run) > 0 && isHan != runIsHan {
			emitRun()
		}
		runIsHan = isHan
		run = append(run, r)
	}
	emitRun()

	return runs
}
