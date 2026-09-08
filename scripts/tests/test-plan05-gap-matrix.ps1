param([string]$MatrixPath = 'docs/maintenance/plan05-mature-software-gap-matrix.md')

$ErrorActionPreference = 'Stop'

$validator = Join-Path $PSScriptRoot '..\test-plan05-gap-matrix.ps1'
$validator = (Resolve-Path -LiteralPath $validator).Path
$sourceMatrix = (Resolve-Path -LiteralPath $MatrixPath).Path
$temporaryRoot = Join-Path ([System.IO.Path]::GetTempPath()) "plan05-gap-matrix-$PID"
$passedCases = 0

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

try {
    New-Item -ItemType Directory -Path $temporaryRoot | Out-Null
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

    Assert-ValidatorSuccess 'committed matrix' (Write-Fixture 'committed-matrix' $matrix)
    Write-Host "Plan 05 gap matrix regression harness passed: $passedCases cases."
}
finally {
    if (Test-Path -LiteralPath $temporaryRoot) {
        Remove-Item -LiteralPath $temporaryRoot -Recurse -Force
    }
}
