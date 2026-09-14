package main

import (
	"encoding/json"
	"testing"

	"github.com/stretchr/testify/require"
)

func TestValidateActorsRejectsMissingAdmin(t *testing.T) {
	err := validateActors(map[string]Actor{"tenant-a-viewer": {Role: "VIEWER"}})
	require.ErrorContains(t, err, "tenant-a-admin")
}

func TestValidateActorsRequiresExactTaskThreeActors(t *testing.T) {
	actors := map[string]Actor{
		"tenant-a-viewer":      {Role: "VIEWER"},
		"tenant-a-contributor": {Role: "CONTRIBUTOR"},
		"tenant-a-admin":       {Role: "ADMIN"},
		"tenant-b-admin":       {Role: "ADMIN"},
	}
	require.NoError(t, validateActors(actors))
	delete(actors, "tenant-b-admin")
	require.Error(t, validateActors(actors))
}

func TestActorManifestContainsAliasesOnly(t *testing.T) {
	manifest := actorManifest{
		Actors: map[string]Actor{
			"tenant-a-viewer": {Role: "VIEWER"},
		},
	}
	raw, err := json.Marshal(manifest)
	require.NoError(t, err)
	require.NotContains(t, string(raw), "password")
	require.NotContains(t, string(raw), "jwt")
	require.NotContains(t, string(raw), "database")
	require.NotContains(t, string(raw), "id")
}

func TestParseFlagsRejectsUnexpectedArguments(t *testing.T) {
	_, err := parseFlags([]string{"--database-url", "postgres://private", "--manifest-path", "actors.json", "--password", "secret"})
	require.Error(t, err)
}
