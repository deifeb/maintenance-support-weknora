//go:build !cgo

package types

import (
	"reflect"
	"testing"
)

func TestNonCGOJiebaFallback(t *testing.T) {
	if got := Jieba.CutForSearch("", true); len(got) != 0 {
		t.Fatalf("CutForSearch(empty) = %v, want no tokens", got)
	}

	want := []string{"航空发动机", "航空", "空发", "发动", "动机", "maintenance"}
	got := Jieba.CutForSearch("航空发动机 maintenance", true)
	if !reflect.DeepEqual(got, want) {
		t.Fatalf("CutForSearch() = %v, want %v", got, want)
	}

	if repeat := Jieba.CutForSearch("航空发动机 maintenance", true); !reflect.DeepEqual(repeat, got) {
		t.Fatalf("CutForSearch() repeated = %v, want %v", repeat, got)
	}
}

func TestNonCGOJiebaFallbackCut(t *testing.T) {
	want := []string{"航空发动机"}
	if got := Jieba.Cut("航空发动机", true); !reflect.DeepEqual(got, want) {
		t.Fatalf("Cut() = %v, want %v", got, want)
	}
}

func TestNonCGOJiebaFallbackSearchTokenEdges(t *testing.T) {
	tests := []struct {
		name string
		text string
		want []string
	}{
		{"deduplicates repeated Han bigrams", "人人人", []string{"人人人", "人人"}},
		{"splits punctuation separated Han", "甲乙，丙丁", []string{"甲乙", "甲乙", "丙丁", "丙丁"}},
		{"keeps digits and accented Latin in their runs", "P-12 café", []string{"P", "12", "café"}},
		{"keeps other Unicode letter runs", "Москва 東京", []string{"Москва", "東京", "東京"}},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			if got := Jieba.CutForSearch(tt.text, true); !reflect.DeepEqual(got, tt.want) {
				t.Fatalf("CutForSearch(%q) = %v, want %v", tt.text, got, tt.want)
			}
		})
	}
}
