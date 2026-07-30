//go:build !cgo

package utils

import (
	"errors"

	pg_query "github.com/pganalyze/pg_query_go/v6"
)

var errPostgresParserRequiresCGO = errors.New("PostgreSQL parser requires cgo")

func parsePostgresSQL(string) (*pg_query.ParseResult, error) {
	return nil, errPostgresParserRequiresCGO
}

func deparsePostgresSQL(*pg_query.ParseResult) (string, error) {
	return "", errPostgresParserRequiresCGO
}
