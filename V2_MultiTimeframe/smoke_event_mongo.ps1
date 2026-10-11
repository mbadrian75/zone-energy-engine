param(
    [string]$PythonPath = (Join-Path $PSScriptRoot '..\.venv\Scripts\python.exe'),
    [string]$Database = 'market_data',
    [string]$RunId = ('v2-events-jan2025-' + [guid]::NewGuid().ToString('N'))
)
$ErrorActionPreference = 'Stop'
if (-not (Test-Path -LiteralPath $PythonPath -PathType Leaf)) {
    throw 'Python executable missing. Supply -PythonPath with your server venv path.'
}
$taskPython = (Resolve-Path -LiteralPath $PythonPath).Path
$savedPythonPath = $env:PYTHONPATH
$savedNoBytecode = $env:PYTHONDONTWRITEBYTECODE
$savedLive = $env:ZONE_ENERGY_LIVE_MONGO_TEST
$savedTestDatabase = $env:ZONE_ENERGY_TEST_DATABASE
Push-Location (Split-Path $PSScriptRoot -Parent)
try {
    $env:PYTHONDONTWRITEBYTECODE = '1'
    $env:PYTHONPATH = 'V2_MultiTimeframe;V1/src'
    $env:ZONE_ENERGY_LIVE_MONGO_TEST = '1'
    $env:ZONE_ENERGY_TEST_DATABASE = $Database
    & $taskPython -m unittest discover -s V2_MultiTimeframe/tests -v
    if ($LASTEXITCODE -ne 0) { throw 'Unit/equivalence/live MongoDB tests failed.' }
    & $taskPython V2_MultiTimeframe/run_v1_multitimeframe.py `
        --start 2025-01-01 --end 2025-02-01 `
        --year-candles-h1 5933 --year-candles-h4 1601 --year-candles-d1 313 `
        --database $Database --storage mongodb-events --run-id $RunId `
        --mongo-batch-size 25 --event-batch-size 1000
    if ($LASTEXITCODE -ne 0) { throw 'January replay failed; retain data and use a new run ID.' }
    & $taskPython V2_MultiTimeframe/validate_event_run.py `
        --database $Database --run-id $RunId `
        --reference V2_MultiTimeframe/v2-smoke-2025-01.jsonl
    if ($LASTEXITCODE -ne 0) { throw 'January equivalence validation failed. Do not run long replay.' }
    Write-Host "VALIDATED_SMOKE_RUN_ID=$RunId"
} finally {
    $env:PYTHONPATH = $savedPythonPath
    $env:PYTHONDONTWRITEBYTECODE = $savedNoBytecode
    $env:ZONE_ENERGY_LIVE_MONGO_TEST = $savedLive
    $env:ZONE_ENERGY_TEST_DATABASE = $savedTestDatabase
    Pop-Location
}
