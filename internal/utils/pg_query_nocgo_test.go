//go:build !cgo

package utils

import (
	"strings"
	"testing"
)

func TestParseSQLFailsClosedWithoutCGO(t *testing.T) {
	result := ParseSQL("SELECT 1")

	if result.IsSelect {
		t.Fatal("ParseSQL accepted SQL without the PostgreSQL parser")
	}
	if !strings.Contains(result.ParseError, "requires cgo") {
		t.Fatalf("ParseSQL error %q does not report that PostgreSQL parsing requires cgo", result.ParseError)
	}
}

func TestValidateSQLFailsClosedWithoutCGO(t *testing.T) {
	_, validation := ValidateSQL("SELECT 1", WithSelectOnly())

	if validation.Valid {
		t.Fatal("ValidateSQL accepted unparsed SQL without the PostgreSQL parser")
	}
}
