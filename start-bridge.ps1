# ═══════════════════════════════════════════════════════════════════════
#  D-Cloud  —  Bridge + Frontend Launcher  (run on the BRIDGE machine)
#
#  Before running:
#    1. Edit api-bridge\.env and set NODE_URLS to the real IPs of your
#       3 node machines (the start-node.ps1 script prints each machine's IP).
#    2. Make sure the .venv is set up:
#         cd api-bridge
#         python -m venv .venv
#         .venv\Scripts\Activate.ps1
#         pip install -r requirements.txt
# ═══════════════════════════════════════════════════════════════════════

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$bridgeDir = Join-Path $root "api-bridge"
$frontDir = Join-Path $root "frontend"

# ── Read NODE_URLS from .env ─────────────────────────────────────────
$envFile = Join-Path $bridgeDir ".env"
$nodeUrls = ""
foreach ($line in Get-Content $envFile) {
    if ($line -match "^NODE_URLS\s*=\s*(.+)$") {
        $nodeUrls = $matches[1].Trim()
        break
    }
}

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  D-Cloud Bridge + Frontend" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Node URLs : $nodeUrls"
Write-Host ""

if ($nodeUrls -match "127\.0\.0\.1") {
    Write-Host "  WARNING  NODE_URLS still points to localhost." -ForegroundColor Yellow
    Write-Host "     Edit api-bridge\.env with real machine IPs first." -ForegroundColor Yellow
    Write-Host ""
    Write-Host "  Example .env line:" -ForegroundColor Cyan
    Write-Host "    NODE_URLS=http://192.168.1.10:8001,http://192.168.1.11:8001,http://192.168.1.12:8001"
    Write-Host ""
    $ans = Read-Host "  Continue anyway? (y/N)"
    if ($ans -ne "y" -and $ans -ne "Y") { exit 0 }
}

# ── Verify .venv exists ──────────────────────────────────────────────
$venv = Join-Path $bridgeDir ".venv\Scripts\python.exe"
if (-not (Test-Path $venv)) {
    Write-Host "  [ERROR]  No .venv found. Run:" -ForegroundColor Red
    Write-Host "       cd api-bridge" -ForegroundColor Red
    Write-Host "       python -m venv .venv" -ForegroundColor Red
    Write-Host "       .venv\Scripts\Activate.ps1" -ForegroundColor Red
    Write-Host "       pip install -r requirements.txt" -ForegroundColor Red
    exit 1
}

# ── Ping all nodes before starting ──────────────────────────────────
Write-Host "  Pinging nodes..." -ForegroundColor Cyan
$urls = $nodeUrls -split ","
$allOk = $true
foreach ($url in $urls) {
    $url = $url.Trim()
    try {
        $r = Invoke-WebRequest -Uri "$url/health" -TimeoutSec 3 -UseBasicParsing -ErrorAction Stop
        $json = $r.Content | ConvertFrom-Json
        Write-Host "  [OK]  $url  - $($json.node_id) ($($json.chunks_held) chunks)" -ForegroundColor Green
    }
    catch {
        Write-Host "  [FAIL]  $url  - UNREACHABLE" -ForegroundColor Red
        $allOk = $false
    }
}

if (-not $allOk) {
    Write-Host ""
    Write-Host "  WARNING  One or more nodes are unreachable." -ForegroundColor Yellow
    Write-Host "     Start start-node.ps1 on each machine first." -ForegroundColor Yellow
    $ans = Read-Host "  Start bridge anyway? (y/N)"
    if ($ans -ne "y" -and $ans -ne "Y") { exit 0 }
}

Write-Host ""
Write-Host "  Starting FastAPI bridge on :3000 ..." -ForegroundColor Cyan
Write-Host "  Starting Vite frontend on  :5173 ..." -ForegroundColor Cyan
Write-Host ""

# ── Launch bridge in a new window ────────────────────────────────────
$bridgeCmd = "cd `"$bridgeDir`"; .venv\Scripts\Activate.ps1; uvicorn main:app --host 0.0.0.0 --port 3000"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $bridgeCmd

# ── Give bridge 3 s to bind ──────────────────────────────────────────
Start-Sleep -Seconds 3

# ── Launch frontend in a new window ─────────────────────────────────
$frontCmd = "cd `"$frontDir`"; npm run dev"
Start-Process powershell -ArgumentList "-NoExit", "-Command", $frontCmd

Write-Host "  Bridge  : http://localhost:3000/api/health" -ForegroundColor Green
Write-Host "  Frontend: http://localhost:5173" -ForegroundColor Green
Write-Host ""
Write-Host "  Opening browser..." -ForegroundColor Cyan
Start-Sleep -Seconds 3
Start-Process "http://localhost:5173"