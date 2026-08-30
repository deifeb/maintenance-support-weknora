param()

$ErrorActionPreference = "Stop"

$baseline = "f42db818c27e2e91f185301246c8fd36b2d35fab"
$allowedTask0Changes = @(
    "scripts/plan05/check-reality-baseline.ps1"
)

# The approved baseline must remain in the ancestry of the implementation branch.
# This keeps the check valid after the Task 0 script itself is committed.
git merge-base --is-ancestor $baseline HEAD
if ($LASTEXITCODE -ne 0) {
    throw "Approved Plan 05-5 baseline $baseline is not an ancestor of HEAD. Rebaseline before implementation."
}

$changed = @(
    git diff --name-only "$baseline...HEAD" |
        ForEach-Object { $_.Trim() } |
        Where-Object { $_ -ne "" }
)

$unexpected = @($changed | Where-Object { $_ -notin $allowedTask0Changes })
if ($unexpected.Count -gt 0) {
    throw "Unexpected changes exist before Task 1: $($unexpected -join ', '). Rebaseline or reset before implementation."
}

$required = @(
    "internal/types/message.go",
    "internal/application/repository/message.go",
    "internal/handler/session/qa.go",
    "extensions/maintenance-api/app/services/ai_report_service.py",
    "frontend/src/views/maintenance/reports/ReportCenter.vue"
)

foreach ($path in $required) {
    if (-not (Test-Path $path)) {
        throw "Required baseline file missing: $path"
    }
}

$latestMigration = Get-ChildItem "migrations/versioned/*_*.up.sql" |
    Sort-Object Name |
    Select-Object -Last 1

if ($null -eq $latestMigration) {
    throw "No Core versioned migration files were found."
}

if ($latestMigration.Name -ne "000034_add_attachments.up.sql") {
    throw "Core migration head moved to $($latestMigration.Name); renumber the planned maintenance_cards migration and rebaseline."
}

if (Test-Path "migrations/versioned/000035_add_message_maintenance_cards.up.sql") {
    throw "Migration 000035 is already occupied; renumber the planned maintenance_cards migration and update the implementation plan before coding."
}

Write-Host "Plan 05-5 reality baseline verified."
Write-Host "Approved baseline: $baseline"
Write-Host "Current HEAD: $((git rev-parse HEAD).Trim())"
Write-Host "Core migration head: $($latestMigration.Name)"
Write-Host "Task 1 may begin."
