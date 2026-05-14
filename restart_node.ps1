param (
    [Parameter(Mandatory = $true, HelpMessage = "Enter the node number to restart (1, 2, or 3)")]
    [ValidateSet("1", "2", "3")]
    [string]$NodeNumber
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$bridgeDir = Join-Path $root "api-bridge"
$nodePy = Join-Path $root "node_server.py"
$pythonExe = Join-Path $bridgeDir ".venv\Scripts\python.exe"

$port = "800$NodeNumber"
$nodeId = "node$NodeNumber"

function Launch($title, $cmd) {
    Start-Process powershell -ArgumentList "-NoExit", "-Command", "`$host.ui.RawUI.WindowTitle = '$title'; $cmd"
}

# Kill existing process on that port if any
$pids = (Get-NetTCPConnection -LocalPort $port -EA SilentlyContinue).OwningProcess | Sort-Object -Unique
foreach ($pid2 in $pids) {
    if ($pid2 -and $pid2 -gt 0) {
        Write-Host "Stopping existing process on port $port..." -ForegroundColor Yellow
        Stop-Process -Id $pid2 -Force -EA SilentlyContinue
    }
}

Write-Host "Starting Node $NodeNumber on port $port..." -ForegroundColor Green
Launch "Node $NodeNumber :$port" "& '$pythonExe' '$nodePy' --port $port --node-id $nodeId"
