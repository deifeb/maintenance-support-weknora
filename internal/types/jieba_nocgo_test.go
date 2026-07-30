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
