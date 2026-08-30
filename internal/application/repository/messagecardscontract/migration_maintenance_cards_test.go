package messagecardscontract_test

import (
	"os"
	"path/filepath"
	"strings"
	"testing"

	"github.com/stretchr/testify/require"
)

func repositoryRoot(t *testing.T) string {
	t.Helper()

	root, err := filepath.Abs(
		filepath.Join("..", "..", "..", ".."),
	)
	require.NoError(t, err)
	return root
}

func TestMaintenanceCardsMigrationContract(t *testing.T) {
	root := repositoryRoot(t)

	upPath := filepath.Join(
		root,
		"migrations",
		"versioned",
		"000073_add_message_maintenance_cards.up.sql",
	)
	downPath := filepath.Join(
		root,
		"migrations",
		"versioned",
		"000073_add_message_maintenance_cards.down.sql",
	)

	upBytes, err := os.ReadFile(upPath)
	require.NoError(t, err)
	downBytes, err := os.ReadFile(downPath)
	require.NoError(t, err)

	up := strings.TrimSpace(string(upBytes))
	down := strings.TrimSpace(string(downBytes))

	require.Equal(
		t,
		"ALTER TABLE messages ADD COLUMN IF NOT EXISTS "+
			"maintenance_cards JSONB NOT NULL DEFAULT '[]'::jsonb;",
		up,
	)
	require.Equal(
		t,
		"ALTER TABLE messages DROP COLUMN IF EXISTS maintenance_cards;",
		down,
	)
}
