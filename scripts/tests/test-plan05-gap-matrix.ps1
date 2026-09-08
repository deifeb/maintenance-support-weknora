param(
    [string]$MatrixPath = 'docs/maintenance/plan05-mature-software-gap-matrix.md',
    [string]$TemporaryRoot,
    [switch]$SkipTempOwnershipRegression
)

$ErrorActionPreference = 'Stop'

$validator = Join-Path $PSScriptRoot '..\test-plan05-gap-matrix.ps1'
$validator = (Resolve-Path -LiteralPath $validator).Path
$sourceMatrix = (Resolve-Path -LiteralPath $MatrixPath).Path
$temporaryBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath()).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
$temporaryRoot = if ($TemporaryRoot) { $TemporaryRoot } else { Join-Path $temporaryBase "plan05-gap-matrix-$([guid]::NewGuid())" }
$passedCases = 0

function Test-CanonicalTemporaryTarget([string]$Path) {
    try {
        $canonicalPath = [System.IO.Path]::GetFullPath($Path).TrimEnd([System.IO.Path]::DirectorySeparatorChar, [System.IO.Path]::AltDirectorySeparatorChar)
        $parentPath = [System.IO.Path]::GetDirectoryName($canonicalPath)
        return $parentPath -ieq $temporaryBase -and
            [System.IO.Path]::GetFileName($canonicalPath) -match '^plan05-gap-matrix-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$'
    }
    catch {
        return $false
    }
}

function Throw-Invariant([string]$Name, [string]$Message) {
    throw "$Name`: $Message"
}

function Set-StatusForDomain([string]$Content, [string]$Domain, [string]$Status) {
    $lines = @($Content -split "`r?`n")
    $lineIndex = [array]::FindIndex($lines, [Predicate[string]] { param($line) $line -like "| $Domain |*" })
    if ($lineIndex -lt 0) {
        throw "Fixture setup could not find domain '$Domain'."
    }
    $cells = @($lines[$lineIndex].Split('|'))
    $cells[11] = " $Status "
    $lines[$lineIndex] = $cells -join '|'
    return $lines -join "`n"
}

function Write-Fixture([string]$Name, [string]$Content) {
    $fixturePath = Join-Path $temporaryRoot "$Name.md"
    Set-Content -LiteralPath $fixturePath -Value $Content -Encoding utf8NoBOM
    return $fixturePath
}

function Assert-ValidatorFailure([string]$Name, [string]$FixturePath, [string]$Diagnostic) {
    $output = (& pwsh -NoProfile -File $validator -MatrixPath $FixturePath 2>&1 | Out-String)
    if ($LASTEXITCODE -eq 0) {
        throw "$Name should fail validation, but exited 0."
    }
    if ($output -notmatch [regex]::Escape($Diagnostic)) {
        throw "$Name should report '$Diagnostic', but output was: $output"
    }
    $script:passedCases++
    Write-Host "PASS: $Name"
}

function Assert-ValidatorSuccess([string]$Name, [string]$FixturePath) {
    $output = (& pwsh -NoProfile -File $validator -MatrixPath $FixturePath 2>&1 | Out-String)
    if ($LASTEXITCODE -ne 0) {
        throw "$Name should pass validation, but exited ${LASTEXITCODE}: $output"
    }
    $script:passedCases++
    Write-Host "PASS: $Name"
}

$ownsTemporaryRoot = $false
try {
    try {
        New-Item -ItemType Directory -Path $temporaryRoot -ErrorAction Stop | Out-Null
    }
    catch {
        Throw-Invariant 'TemporaryRootInvariant' "Could not create temporary fixture directory: $temporaryRoot"
    }
    $temporaryRoot = (Resolve-Path -LiteralPath $temporaryRoot).Path
    $ownsTemporaryRoot = $true
    $matrix = Get-Content -LiteralPath $sourceMatrix -Raw -Encoding utf8

    $missingDomain = [regex]::Replace($matrix, '(?m)^\| item master \|.*\r?\n', '', 1)
    Assert-ValidatorFailure 'missing domain' (Write-Fixture 'missing-domain' $missingDomain) 'CoverageInvariant'

    $invalidStatus = [regex]::Replace($matrix, [regex]::Escape('| adopted |'), '| unsupported |', 1)
    Assert-ValidatorFailure 'invalid status' (Write-Fixture 'invalid-status' $invalidStatus) 'StatusInvariant'

    $placeholder = $matrix.Replace('planning evidence', 'TODO planning evidence')
    Assert-ValidatorFailure 'placeholder' (Write-Fixture 'placeholder' $placeholder) 'PlaceholderInvariant'

    $missingDeferredReason = $matrix.Replace('离线客户端、冲突同步和设备管理留待后续阶段 |', ' |')
    Assert-ValidatorFailure 'missing deferred reason' (Write-Fixture 'missing-deferred-reason' $missingDeferredReason) 'DeferredReasonInvariant'

    $misorderedHeader = $matrix.Replace('| 功能域 | 成熟软件能力 |', '| 成熟软件能力 | 功能域 |')
    Assert-ValidatorFailure 'misordered designated header' (Write-Fixture 'misordered-header' $misorderedHeader) 'HeaderInvariant'

    $emptyPage = $matrix.Replace('SparePartsPage', '   ')
    Assert-ValidatorFailure 'empty page cell' (Write-Fixture 'empty-page-cell' $emptyPage) 'TableInvariant'

    $shiftedDomain = $matrix.Replace('| item master | Maximo-inspired controlled item master |', '| Maximo-inspired controlled item master | item master |')
    Assert-ValidatorFailure 'domain shifted to capability column' (Write-Fixture 'shifted-domain' $shiftedDomain) 'CoverageInvariant'

    $malformedSeparator = $matrix.Replace('| --- | --- |', '| -- | --- |')
    Assert-ValidatorFailure 'malformed separator' (Write-Fixture 'malformed-separator' $malformedSeparator) 'TableInvariant'

    $extraLeadingPipe = $matrix.Replace('| item master |', '|| item master |')
    Assert-ValidatorFailure 'extra leading pipe' (Write-Fixture 'extra-leading-pipe' $extraLeadingPipe) 'TableInvariant'

    $uppercaseStatus = [regex]::Replace($matrix, [regex]::Escape('| adopted |'), '| ADOPTED |', 1)
    Assert-ValidatorFailure 'uppercase status' (Write-Fixture 'uppercase-status' $uppercaseStatus) 'StatusInvariant'

    foreach ($nonGoal in @('procurement', 'accounting ledger', 'full WMS', 'offline scanning')) {
        $incorrectNonGoalStatus = Set-StatusForDomain $matrix $nonGoal 'adopted'
        Assert-ValidatorFailure "non-goal $nonGoal must be deferred" (Write-Fixture "non-goal-$($nonGoal.Replace('/', '-').Replace(' ', '-'))" $incorrectNonGoalStatus) 'DeferredStatusInvariant'
    }

    Assert-ValidatorSuccess 'committed matrix' (Write-Fixture 'committed-matrix' $matrix)

    if (-not $SkipTempOwnershipRegression) {
        $unownedRoot = Join-Path ([System.IO.Path]::GetTempPath()) "plan05-gap-matrix-$([guid]::NewGuid())"
        New-Item -ItemType Directory -Path $unownedRoot | Out-Null
        $markerPath = Join-Path $unownedRoot 'must-survive.txt'
        Set-Content -LiteralPath $markerPath -Value 'unowned' -Encoding utf8NoBOM
        try {
            if (-not (Test-CanonicalTemporaryTarget $unownedRoot)) {
                throw 'Fixture setup did not create a canonical temporary target.'
            }
            $output = (& pwsh -NoProfile -File $PSCommandPath -MatrixPath $sourceMatrix -TemporaryRoot $unownedRoot -SkipTempOwnershipRegression 2>&1 | Out-String)
            if ($LASTEXITCODE -eq 0 -or $output -notmatch 'TemporaryRootInvariant') {
                throw "failed temp creation should report TemporaryRootInvariant, but output was: $output"
            }
            if (-not (Test-Path -LiteralPath $markerPath -PathType Leaf)) {
                throw 'failed temp creation deleted an unowned directory.'
            }
            $passedCases++
            Write-Host 'PASS: failed temp creation preserves unowned directory'
        }
        finally {
            Remove-Item -LiteralPath $unownedRoot -Recurse -Force
        }
    }

    Write-Host "Plan 05 gap matrix regression harness passed: $passedCases cases."
}
finally {
    if ($ownsTemporaryRoot -and (Test-CanonicalTemporaryTarget $temporaryRoot) -and
        (Test-Path -LiteralPath $temporaryRoot -PathType Container)) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
