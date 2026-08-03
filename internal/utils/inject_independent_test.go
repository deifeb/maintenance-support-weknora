package utils

import "testing"

func TestInjectAndConditions(t *testing.T) {
	tests := []struct {
		name   string
		sql    string
		filter string
		want   string
	}{
		{
			name:   "existing WHERE with ORDER BY",
			sql:    "SELECT id, title FROM knowledges WHERE parse_status = 'completed' ORDER BY created_at DESC LIMIT 10",
			filter: "knowledges.tenant_id = 123",
			want:   "SELECT id, title FROM knowledges WHERE knowledges.tenant_id = 123 AND (parse_status = 'completed') ORDER BY created_at DESC LIMIT 10",
		},
		{
			name:   "existing WHERE without tail clauses",
			sql:    "SELECT id FROM knowledges WHERE enable_status = 'enabled'",
			filter: "knowledges.deleted_at IS NULL",
			want:   "SELECT id FROM knowledges WHERE knowledges.deleted_at IS NULL AND (enable_status = 'enabled')",
		},
		{
			name:   "no WHERE with ORDER BY",
			sql:    "SELECT id FROM knowledges ORDER BY created_at DESC",
			filter: "knowledges.tenant_id = 123",
			want:   "SELECT id FROM knowledges WHERE knowledges.tenant_id = 123 ORDER BY created_at DESC",
		},
	}

	for _, tt := range tests {
		t.Run(tt.name, func(t *testing.T) {
			got := InjectAndConditions(tt.sql, tt.filter)
			if got != tt.want {
				t.Fatalf("InjectAndConditions() = %q, want %q", got, tt.want)
			}
		})
	}
}

func BenchmarkInjectAndConditions(b *testing.B) {
	const sql = "SELECT id, title FROM docs WHERE status = 'active' ORDER BY created_at LIMIT 50"
	for i := 0; i < b.N; i++ {
		_ = InjectAndConditions(sql, "tenant_id = 1")
	}
}

func BenchmarkCheckSQLInjectionRisks(b *testing.B) {
	const where = "status = 'active' AND name LIKE '%foo%' AND (deleted_at IS NULL OR archived = false)"
	for i := 0; i < b.N; i++ {
		_ = checkSQLInjectionRisks(where)
	}
}
