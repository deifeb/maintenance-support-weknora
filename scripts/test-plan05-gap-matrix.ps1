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
$requiredDeferredDomains = @('procurement', 'accounting ledger', 'full WMS', 'offline scanning')

function Throw-Invariant([string]$Name, [string]$Message) {
    throw "$Name`: $Message"
}

function Get-StrictTableCells([string]$Line, [string]$Context) {
    $trimmedLine = $Line.Trim()
    if ($trimmedLine -notmatch '^\|[^|].*[^|]\|$') {
        Throw-Invariant 'TableInvariant' "$Context must use exactly one leading and trailing boundary pipe: $Line"
    }
    return @($trimmedLine.Substring(1, $trimmedLine.Length - 2).Split('|') | ForEach-Object { $_.Trim() })
}

if (-not (Test-Path -LiteralPath $MatrixPath -PathType Leaf)) {
    Throw-Invariant 'MatrixPathInvariant' "Matrix file not found: $MatrixPath"
}

$content = Get-Content -LiteralPath $MatrixPath -Raw -Encoding utf8
$lines = @($content -split "`r?`n")
$headerIndex = -1
for ($index = 0; $index -lt ($lines.Count - 1); $index++) {
    if ($lines[$index] -match '^\|' -and $lines[$index + 1] -match '^\|\s*-+') {
        $headerIndex = $index
        break
    }
}

if ($headerIndex -lt 0) {
    Throw-Invariant 'HeaderInvariant' 'Missing Markdown table header.'
}

$headerCells = Get-StrictTableCells $lines[$headerIndex] 'Header row'
if ($headerCells.Count -ne $requiredHeaders.Count -or
    ($headerCells -join "`0") -cne ($requiredHeaders -join "`0")) {
    Throw-Invariant 'HeaderInvariant' 'Required table headers are missing or out of order.'
}

$separatorCells = Get-StrictTableCells $lines[$headerIndex + 1] 'Separator row'
if ($separatorCells.Count -ne $requiredHeaders.Count -or
    @($separatorCells | Where-Object { $_ -notmatch '^:?-{3,}:?$' }).Count -gt 0) {
    Throw-Invariant 'TableInvariant' 'Separator row must contain exactly 12 Markdown separator cells.'
}

if ($content -match '(?i)(?<![A-Z])(?:TBD|TODO)(?![A-Z])|待补充|N/A') {
    Throw-Invariant 'PlaceholderInvariant' 'Matrix contains an unfilled marker.'
}

$dataRows = @(
    for ($index = $headerIndex + 2; $index -lt $lines.Count -and -not [string]::IsNullOrWhiteSpace($lines[$index]); $index++) {
        if ($lines[$index] -notmatch '^\|') {
            Throw-Invariant 'TableInvariant' "Data row is missing a leading boundary pipe: $($lines[$index])"
        }
        $lines[$index]
    }
)

if ($dataRows.Count -eq 0) {
    Throw-Invariant 'TableInvariant' 'Matrix contains no data rows.'
}

$parsedRows = @()
foreach ($line in $dataRows) {
    $cells = Get-StrictTableCells $line 'Data row'
    if ($cells.Count -ne $requiredHeaders.Count) {
        Throw-Invariant 'TableInvariant' "Expected $($requiredHeaders.Count) columns, found $($cells.Count): $line"
    }

    $status = $cells[10]
    if ($status -cnotin $allowedStatuses) {
        Throw-Invariant 'StatusInvariant' "Unsupported status '$status' for capability '$($cells[0])'."
    }
    if ($status -ceq 'deferred' -and [string]::IsNullOrWhiteSpace($cells[11])) {
        Throw-Invariant 'DeferredReasonInvariant' "Deferred capability '$($cells[0])' has no reason."
    }
    if (@($cells | Where-Object { [string]::IsNullOrWhiteSpace($_) }).Count -gt 0) {
        Throw-Invariant 'TableInvariant' "Row contains an empty cell: $line"
    }
    if ($cells[0] -cin $requiredDeferredDomains -and $status -cne 'deferred') {
        Throw-Invariant 'DeferredStatusInvariant' "Non-goal capability '$($cells[0])' must be deferred."
    }
    $parsedRows += ,$cells
}

foreach ($capability in $requiredCapabilities) {
    if (-not ($parsedRows | Where-Object { $_[0] -ceq $capability })) {
        Throw-Invariant 'CoverageInvariant' "Missing required capability: $capability"
    }
}

Write-Host "Plan 05 gap matrix validated: $($dataRows.Count) domains."
