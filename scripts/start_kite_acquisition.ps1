param(
    [ValidateSet("probe", "download")]
    [string]$Mode = "probe",
    [Parameter(Mandatory = $true)]
    [string]$ExportDirectory,
    [string]$SymbolsFile,
    [string]$ProvenanceFile,
    [string]$HistoryStart,
    [string]$HistoryEnd,
    [string]$LegacyTokenFile,
    [string]$LegacyTokenSha256,
    [string]$SeriesRouteEvidenceFile,
    [string]$SeriesRouteEvidenceSha256,
    [string]$RunId
)

$ErrorActionPreference = "Stop"
if ($Mode -eq "download") {
    if ([bool]$HistoryStart -ne [bool]$HistoryEnd) {
        throw "-HistoryStart and -HistoryEnd must be supplied together."
    }
    if ([bool]$LegacyTokenFile -ne [bool]$LegacyTokenSha256) {
        throw "-LegacyTokenFile and -LegacyTokenSha256 must be supplied together."
    }
    if ($LegacyTokenSha256 -and $LegacyTokenSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "LegacyTokenSha256 must be a SHA-256 digest."
    }
    if ([bool]$SeriesRouteEvidenceFile -ne [bool]$SeriesRouteEvidenceSha256) {
        throw "-SeriesRouteEvidenceFile and -SeriesRouteEvidenceSha256 must be supplied together."
    }
    if ($SeriesRouteEvidenceSha256 -and $SeriesRouteEvidenceSha256 -notmatch '^[0-9a-fA-F]{64}$') {
        throw "SeriesRouteEvidenceSha256 must be a SHA-256 digest."
    }
    if (($LegacyTokenFile -or $SeriesRouteEvidenceFile) -and ($HistoryStart -ne "2022-11-29" -or $HistoryEnd -ne "2022-12-30")) {
        throw "Candidate routes require the exact bounded range 2022-11-29 through 2022-12-30."
    }
}
elseif ($HistoryStart -or $HistoryEnd -or $LegacyTokenFile -or $LegacyTokenSha256 -or $SeriesRouteEvidenceFile -or $SeriesRouteEvidenceSha256) {
    throw "Probe mode does not accept download range or legacy-token inputs."
}
New-Item -ItemType Directory -Path $ExportDirectory -Force | Out-Null
$resolvedExport = (Resolve-Path -LiteralPath $ExportDirectory).Path
$compose = Join-Path $PSScriptRoot "..\deploy\kite-acquire.compose.yaml"
$effectiveRunId = if ($RunId) { $RunId } else { (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmss.fffffffZ") }
if ($effectiveRunId -notmatch '^[A-Za-z0-9_-]{1,80}$') { throw "RunId contains unsafe characters." }
$project = "kite-acquire-$($effectiveRunId.ToLowerInvariant())"
$symbolName = $null
$legacyName = $null
$expectedLegacyHash = $null
$seriesEvidenceName = $null
$expectedSeriesEvidenceHash = $null
if ($Mode -eq "download") {
    if (-not $SymbolsFile) { throw "Download mode requires -SymbolsFile." }
    $resolvedSymbols = (Resolve-Path -LiteralPath $SymbolsFile).Path
    if (-not $ProvenanceFile) { $ProvenanceFile = Join-Path (Split-Path $resolvedSymbols) "provenance.json" }
    $resolvedProvenance = (Resolve-Path -LiteralPath $ProvenanceFile).Path
    $symbolName = "requested-symbols-$effectiveRunId.txt"
    $symbolTarget = Join-Path $resolvedExport $symbolName
    if (Test-Path -LiteralPath $symbolTarget) {
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedSymbols).Hash
        $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $symbolTarget).Hash
        if ($sourceHash -ne $targetHash) { throw "Requested-symbol archive exists with different bytes." }
    }
    else {
        Copy-Item -LiteralPath $resolvedSymbols -Destination $symbolTarget
    }
    $provenanceName = "provenance-$effectiveRunId.json"
    $provenanceTarget = Join-Path $resolvedExport $provenanceName
    if (Test-Path -LiteralPath $provenanceTarget) {
        $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedProvenance).Hash
        $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $provenanceTarget).Hash
        if ($sourceHash -ne $targetHash) { throw "Provenance archive exists with different bytes." }
    }
    else {
        Copy-Item -LiteralPath $resolvedProvenance -Destination $provenanceTarget
    }
    if ($LegacyTokenFile) {
        $resolvedLegacy = (Resolve-Path -LiteralPath $LegacyTokenFile).Path
        $legacyName = "legacy-token-routes-$effectiveRunId.json"
        $legacyTarget = Join-Path $resolvedExport $legacyName
        if (Test-Path -LiteralPath $legacyTarget) {
            $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedLegacy).Hash
            $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $legacyTarget).Hash
            if ($sourceHash -ne $targetHash) { throw "Legacy-token archive exists with different bytes." }
        }
        else {
            Copy-Item -LiteralPath $resolvedLegacy -Destination $legacyTarget
        }
        $expectedLegacyHash = $LegacyTokenSha256.ToLowerInvariant()
        $archivedLegacyHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $legacyTarget).Hash.ToLowerInvariant()
        if ($archivedLegacyHash -ne $expectedLegacyHash) {
            throw "Legacy-token archive does not match the reviewed SHA-256."
        }
    }
    if ($SeriesRouteEvidenceFile) {
        $resolvedSeriesEvidence = (Resolve-Path -LiteralPath $SeriesRouteEvidenceFile).Path
        $seriesEvidenceName = "series-route-evidence-$effectiveRunId.json"
        $seriesEvidenceTarget = Join-Path $resolvedExport $seriesEvidenceName
        if (Test-Path -LiteralPath $seriesEvidenceTarget) {
            $sourceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $resolvedSeriesEvidence).Hash
            $targetHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $seriesEvidenceTarget).Hash
            if ($sourceHash -ne $targetHash) { throw "Series-route evidence archive exists with different bytes." }
        }
        else {
            Copy-Item -LiteralPath $resolvedSeriesEvidence -Destination $seriesEvidenceTarget
        }
        $expectedSeriesEvidenceHash = $SeriesRouteEvidenceSha256.ToLowerInvariant()
        $archivedSeriesEvidenceHash = (Get-FileHash -Algorithm SHA256 -LiteralPath $seriesEvidenceTarget).Hash.ToLowerInvariant()
        if ($archivedSeriesEvidenceHash -ne $expectedSeriesEvidenceHash) {
            throw "Series-route evidence archive does not match the reviewed SHA-256."
        }
    }
}

$existingWorker = & docker ps -aq --filter "name=^/$project-worker$"
if ($LASTEXITCODE -ne 0) { throw "Docker is unavailable; start Docker Desktop before acquisition." }
if ($existingWorker) { throw "This acquisition run already owns a container; resolve it before resuming." }

$env:KITE_EXPORT_DIR = $resolvedExport
try {
    docker compose -p $project -f $compose build kite-proxy kite-acquirer
    if ($LASTEXITCODE -ne 0) { throw "Kite acquisition image build failed." }
    docker compose -p $project -f $compose up -d --wait kite-proxy
    if ($LASTEXITCODE -ne 0) { throw "Kite acquisition proxy failed to start." }
    $arguments = @("run", "--rm", "--name", "$project-worker", "kite-acquirer", "--mode", $Mode, "--export", "/export", "--run-id", $effectiveRunId)
    if ($Mode -eq "download") {
        $arguments += @("--symbols-file", "/export/$symbolName", "--provenance", "/export/$provenanceName")
        if ($HistoryStart) {
            $arguments += @("--history-start", $HistoryStart, "--history-end", $HistoryEnd)
        }
        if ($legacyName) {
            $arguments += @("--legacy-token-file", "/export/$legacyName", "--legacy-token-sha256", $expectedLegacyHash)
        }
        if ($seriesEvidenceName) {
            $arguments += @("--series-route-evidence-file", "/export/$seriesEvidenceName", "--series-route-evidence-sha256", $expectedSeriesEvidenceHash)
        }
    }
    & docker compose -p $project -f $compose @arguments
    if ($LASTEXITCODE -eq 3) {
        Write-Host "Acquisition completed with quarantined chunks. Review report.json before qualification."
        exit 3
    }
    if ($LASTEXITCODE -ne 0) { throw "Kite acquisition exited with code $LASTEXITCODE." }
}
finally {
    docker compose -p $project -f $compose down
    Remove-Item Env:KITE_EXPORT_DIR -ErrorAction SilentlyContinue
}
