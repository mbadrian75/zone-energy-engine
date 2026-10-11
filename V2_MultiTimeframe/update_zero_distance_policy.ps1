param(
    [Parameter(Mandatory = $true)]
    [ValidatePattern('^[a-f0-9]{40}$')]
    [string]$Revision,
    [string]$PythonPath = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
    [string]$Database = 'market_data'
)
$ErrorActionPreference = 'Stop'
$files = @(
    'zero_distance_policy.py',
    'v1_adapter.py',
    'mongo_event_repository.py',
    'run_v1_multitimeframe.py',
    'validate_event_run.py',
    'smoke_event_mongo.ps1',
    'tests/test_zero_distance_policy.py',
    'tests/test_mongo_event_repository.py',
    'tests/test_event_live_mongo.py',
    'tests/test_replay_failure_diagnostics.py',
    'diagnostics/diagnose_replay.py'
)
$stagePath = Join-Path $PSScriptRoot ('.policy-download-' + [guid]::NewGuid().ToString('N'))
$resolvedStage = [System.IO.Path]::GetFullPath($stagePath)
$resolvedV2 = [System.IO.Path]::GetFullPath($PSScriptRoot).TrimEnd('\') + '\'
if (-not $resolvedStage.StartsWith($resolvedV2, [System.StringComparison]::OrdinalIgnoreCase)) {
    throw 'Download staging path must stay inside V2.'
}
New-Item -ItemType Directory -Path $resolvedStage | Out-Null
try {
    # Download every file first. Failed downloads leave installed code unchanged.
    foreach ($relative in $files) {
        $staged = Join-Path $resolvedStage $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $staged -Parent) | Out-Null
        $uri = "https://raw.githubusercontent.com/mbadrian75/zone-energy-engine/$Revision/V2_MultiTimeframe/$relative"
        Invoke-WebRequest -UseBasicParsing -Uri $uri -OutFile $staged -ErrorAction Stop
    }
    foreach ($relative in $files) {
        $target = Join-Path $PSScriptRoot $relative
        New-Item -ItemType Directory -Force -Path (Split-Path $target -Parent) | Out-Null
        Copy-Item -LiteralPath (Join-Path $resolvedStage $relative) -Destination $target -Force
    }
    Write-Host "Updated V2 policy files from $Revision. Running fresh January smoke."
    & (Join-Path $PSScriptRoot 'smoke_event_mongo.ps1') -PythonPath $PythonPath -Database $Database
} finally {
    # Remove only the known files and empty directories from our checked staging
    # path. No recursive delete, and no cleanup of runs or market data.
    foreach ($relative in $files) {
        $staged = Join-Path $resolvedStage $relative
        if (Test-Path -LiteralPath $staged -PathType Leaf) {
            Remove-Item -LiteralPath $staged -ErrorAction SilentlyContinue
        }
    }
    foreach ($relative in @('tests', 'diagnostics')) {
        $directory = Join-Path $resolvedStage $relative
        if ((Test-Path -LiteralPath $directory -PathType Container) -and
            (Get-ChildItem -LiteralPath $directory -Force | Measure-Object).Count -eq 0) {
            Remove-Item -LiteralPath $directory -ErrorAction SilentlyContinue
        }
    }
    if ((Get-ChildItem -LiteralPath $resolvedStage -Force | Measure-Object).Count -eq 0) {
        Remove-Item -LiteralPath $resolvedStage -ErrorAction SilentlyContinue
    }
}
