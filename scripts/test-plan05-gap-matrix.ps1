param([string]$MatrixPath = 'docs/maintenance/plan05-mature-software-gap-matrix.md')
$ErrorActionPreference = 'Stop'
$allowedStatuses = @('adopted', 'adapted', 'partial', 'deferred')

$requiredHeaders = @(
    '功能域', '成熟软件能力', '本项目必要性', '现有能力', 'Plan 05 实现', '前端页面',
    '后端接口', '数据表', '权限', '验收案例', '状态', '延后原因'
)
$requiredCapabilities = @(
    'item master', 'storeroom', 'balance', 'reservation', 'issue/return', 'transfer',
    'stocktake', 'repairable asset', 'maintenance task material linkage',
    'stock/non-stock distinction', 'availability check', 'high-priority reassignment',
    'warehouse/location/lot/serial reservation', 'pick/issue', 'return', 'procurement',
    'accounting ledger', 'full WMS', 'offline scanning'
)

function Throw-Invariant([string]$Name, [string]$Message) {
    throw "$Name`: $Message"
}

if (-not (Test-Path -LiteralPath $MatrixPath -PathType Leaf)) {
    Throw-Invariant 'MatrixPathInvariant' "Matrix file not found: $MatrixPath"
}

$content = Get-Content -LiteralPath $MatrixPath -Raw -Encoding utf8
foreach ($header in $requiredHeaders) {
    if ($content -notmatch [regex]::Escape("| $header |")) {
        Throw-Invariant 'HeaderInvariant' "Missing required header: $header"
    }
}

foreach ($capability in $requiredCapabilities) {
    if ($content -notmatch [regex]::Escape("| $capability |")) {
        Throw-Invariant 'CoverageInvariant' "Missing required capability: $capability"
    }
}

if ($content -match '(?i)(?<![A-Z])(?:TBD|TODO)(?![A-Z])|待补充|N/A') {
    Throw-Invariant 'PlaceholderInvariant' 'Matrix contains an unfilled marker.'
}

$dataRows = @(
    $content -split "`r?`n" |
        Where-Object { $_ -match '^\|' } |
        Where-Object { $_ -notmatch '^\|\s*-+' } |
        Select-Object -Skip 1
)

if ($dataRows.Count -eq 0) {
    Throw-Invariant 'TableInvariant' 'Matrix contains no data rows.'
}

foreach ($line in $dataRows) {
    $cells = @($line.Trim().Trim('|').Split('|') | ForEach-Object { $_.Trim() })
    if ($cells.Count -ne $requiredHeaders.Count) {
        Throw-Invariant 'TableInvariant' "Expected $($requiredHeaders.Count) columns, found $($cells.Count): $line"
    }
    if ($cells | Where-Object { [string]::IsNullOrWhiteSpace($_) }) {
        Throw-Invariant 'TableInvariant' "Row contains an empty cell: $line"
    }

    $status = $cells[10]
    if ($status -notin $allowedStatuses) {
        Throw-Invariant 'StatusInvariant' "Unsupported status '$status' for capability '$($cells[0])'."
    }
    if ($status -eq 'deferred' -and [string]::IsNullOrWhiteSpace($cells[11])) {
        Throw-Invariant 'DeferredReasonInvariant' "Deferred capability '$($cells[0])' has no reason."
    }
}

Write-Host "Plan 05 gap matrix validated: $($dataRows.Count) domains."
