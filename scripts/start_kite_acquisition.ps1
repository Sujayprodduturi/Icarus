param(
    [ValidateSet("probe", "download")]
    [string]$Mode = "probe",
    [Parameter(Mandatory = $true)]
    [string]$ExportDirectory,
    [string]$SymbolsFile,
    [string]$ProvenanceFile,
    [string]$RunId
)

$ErrorActionPreference = "Stop"
New-Item -ItemType Directory -Path $ExportDirectory -Force | Out-Null
$resolvedExport = (Resolve-Path -LiteralPath $ExportDirectory).Path
$compose = Join-Path $PSScriptRoot "..\deploy\kite-acquire.compose.yaml"
$effectiveRunId = if ($RunId) { $RunId } else { (Get-Date).ToUniversalTime().ToString("yyyyMMddTHHmmss.fffffffZ") }
if ($effectiveRunId -notmatch '^[A-Za-z0-9_-]{1,80}$') { throw "RunId contains unsafe characters." }
$project = "kite-acquire-$($effectiveRunId.ToLowerInvariant())"
$existingWorker = & docker ps -aq --filter "name=^/$project-worker$"
if ($LASTEXITCODE -ne 0) { throw "Docker is unavailable; start Docker Desktop before acquisition." }
if ($existingWorker) { throw "This acquisition run already owns a container; resolve it before resuming." }
$symbolName = $null
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
}

$env:KITE_EXPORT_DIR = $resolvedExport
try {
    docker compose -p $project -f $compose build kite-proxy kite-acquirer
    if ($LASTEXITCODE -ne 0) { throw "Kite acquisition image build failed." }
    docker compose -p $project -f $compose up -d --wait kite-proxy
    if ($LASTEXITCODE -ne 0) { throw "Kite acquisition proxy failed to start." }
    $arguments = @("run", "--rm", "--name", "$project-worker", "kite-acquirer", "--mode", $Mode, "--export", "/export", "--run-id", $effectiveRunId)
    if ($Mode -eq "download") {
        $arguments += @("--symbols-file", "/export/$symbolName", "--provenance", "/export/$provenanceName")
    }
    & docker compose -p $project -f $compose @arguments
    if ($LASTEXITCODE -ne 0) { throw "Kite acquisition exited with code $LASTEXITCODE." }
}
finally {
    docker compose -p $project -f $compose down
    Remove-Item Env:KITE_EXPORT_DIR -ErrorAction SilentlyContinue
}
