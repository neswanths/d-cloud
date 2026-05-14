# -----------------------------------------------------------------------
#  D-Cloud  --  Smart Launcher  (start.ps1)
#
#  USAGE:  .\start.ps1
#
#  Tries hotspot/LAN mode first. If any nodes are unreachable,
#  offers a one-key fallback to single-machine mode so you never crash.
#
#  PREREQUISITES (run once):
#    cd api-bridge
#    python -m venv .venv
#    .venv\Scripts\Activate.ps1
#    pip install -r requirements.txt
#    cd ..\frontend
#    npm install
# -----------------------------------------------------------------------

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$bridgeDir = Join-Path $root "api-bridge"
$frontDir = Join-Path $root "frontend"
$envFile = Join-Path $bridgeDir ".env"
$nodePy = Join-Path $root "node_server.py"
$venv = Join-Path $bridgeDir ".venv\Scripts\python.exe"
$pythonExe = $venv

# -- Banner ------------------------------------------------------------
Clear-Host
Write-Host ""
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host "            D-Cloud  --  Smart Launcher" -ForegroundColor Cyan
Write-Host "   Tries hotspot/LAN mode -> auto-falls back locally" -ForegroundColor Cyan
Write-Host "=======================================================" -ForegroundColor Cyan
Write-Host ""

# -- Check prerequisites -----------------------------------------------
if (-not (Test-Path $venv)) {
    Write-Host "  [ERROR]  Python venv not found in api-bridge\.venv" -ForegroundColor Red
    Write-Host "  Run:"  -ForegroundColor Yellow
    Write-Host "    cd api-bridge" -ForegroundColor Yellow
    Write-Host "    python -m venv .venv" -ForegroundColor Yellow
    Write-Host "    .venv\Scripts\Activate.ps1" -ForegroundColor Yellow
    Write-Host "    pip install -r requirements.txt" -ForegroundColor Yellow
    pause; exit 1
}

# -- Read current NODE_URLS from .env ---------------------------------
$nodeUrls = ""
foreach ($line in Get-Content $envFile) {
    if ($line -match "^NODE_URLS\s*=\s*(.+)$") {
        $nodeUrls = $matches[1].Trim()
        break
    }
}
$urls = ($nodeUrls -split ",") | ForEach-Object { $_.Trim() }

Write-Host "  Current NODE_URLS:" -ForegroundColor DarkGray
foreach ($u in $urls) { Write-Host "    $u" -ForegroundColor DarkGray }
Write-Host ""

# -- Helper: test one node ---------------------------------------------
function Test-Node($url) {
    try {
        $r = Invoke-WebRequest -Uri "$url/health" -TimeoutSec 3 -UseBasicParsing -EA Stop
        $j = $r.Content | ConvertFrom-Json
        return @{ ok = $true; info = $j.node_id }
    }
    catch {
        return @{ ok = $false; info = $null }
    }
}

# -- Helper: launch a named PowerShell window -------------------------
function Launch($title, $cmd) {
    Start-Process powershell `
        -ArgumentList "-NoExit", "-Command", "`$host.ui.RawUI.WindowTitle = '$title'; $cmd"
}

# -- Helper: free ports ------------------------------------------------
function Free-Ports($portList) {
    foreach ($p in $portList) {
        $pids2 = (Get-NetTCPConnection -LocalPort $p -EA SilentlyContinue).OwningProcess | Sort-Object -Unique
        foreach ($pid2 in $pids2) {
            if ($pid2 -and $pid2 -gt 0) {
                Stop-Process -Id $pid2 -Force -EA SilentlyContinue
            }
        }
    }
}

# =======================================================================
#  PHASE 1: Try hotspot / LAN nodes
# =======================================================================

Write-Host "  Phase 1: Testing LAN/hotspot nodes..." -ForegroundColor Cyan
Write-Host ""

$failedUrls = @()
foreach ($url in $urls) {
    $result = Test-Node $url
    if ($result.ok) {
        Write-Host "  [OK]   $url -- $($result.info)" -ForegroundColor Green
    }
    else {
        Write-Host "  [FAIL] $url -- unreachable" -ForegroundColor Red
        $failedUrls += $url
    }
}

Write-Host ""

# -- All nodes online -> proceed normally ------------------------------
if ($failedUrls.Count -eq 0) {
    Write-Host "  All nodes reachable! Starting bridge + frontend..." -ForegroundColor Green
    Write-Host ""

    Free-Ports @(3000, 5173)
    Start-Sleep -Milliseconds 500

    $bridgeCmd = "cd '$bridgeDir'; & '$pythonExe' -m uvicorn main:app --host 0.0.0.0 --port 3000"
    Launch "Bridge :3000" $bridgeCmd
    Start-Sleep -Seconds 3

    Launch "Frontend :5173" "cd '$frontDir'; npm run dev"
    Start-Sleep -Seconds 3

    Write-Host "  Bridge   : http://localhost:3000/api/health" -ForegroundColor Green
    Write-Host "  Frontend : http://localhost:5173"            -ForegroundColor Green
    Start-Process http://localhost:5173
    exit 0
}

# =======================================================================
#  PHASE 2: Some nodes failed -> offer options
# =======================================================================

Write-Host "  $($failedUrls.Count) node(s) unreachable." -ForegroundColor Yellow
Write-Host ""
Write-Host "  What would you like to do?" -ForegroundColor White
Write-Host "    [1]  Auto-scan this machine's subnet and update NODE_URLS (auto-discover)"
Write-Host "    [2]  Switch to SINGLE-MACHINE mode  (safest -- no LAN needed)"
Write-Host "    [3]  Continue with LAN anyway         (use only reachable nodes)"
Write-Host "    [Q]  Quit"
Write-Host ""

$choice = Read-Host "  Enter choice [1/2/3/Q]"
Write-Host ""

# -- Option 1: Auto-discover ------------------------------------------
if ($choice -eq "1") {
    Write-Host "  Scanning subnet for D-Cloud nodes (port 8001)..." -ForegroundColor Cyan
    $discoverPy = Join-Path $root "auto-discover.py"
    if (-not (Test-Path $discoverPy)) {
        Write-Host "  auto-discover.py not found -- switching to single-machine mode." -ForegroundColor Yellow
        $choice = "2"
    }
    else {
        & $pythonExe $discoverPy
        Write-Host ""
        $retry = Read-Host "  Retry with updated NODE_URLS? (y/N)"
        if ($retry -eq "y" -or $retry -eq "Y") {
            # Re-read env and restart the ping loop
            Write-Host "  Re-testing nodes..." -ForegroundColor Cyan
            $nodeUrls = ""
            foreach ($line in Get-Content $envFile) {
                if ($line -match "^NODE_URLS\s*=\s*(.+)$") { $nodeUrls = $matches[1].Trim(); break }
            }
            $urls = ($nodeUrls -split ",") | ForEach-Object { $_.Trim() }
            $allOk = $true
            foreach ($url in $urls) {
                $r = Test-Node $url
                if ($r.ok) { Write-Host "  [OK]   $url" -ForegroundColor Green }
                else { Write-Host "  [FAIL] $url" -ForegroundColor Red; $allOk = $false }
            }
            if (-not $allOk) {
                Write-Host ""
                Write-Host "  Still failing. Switching to single-machine mode." -ForegroundColor Yellow
                $choice = "2"
            }
        }
        else {
            $choice = "2"
        }
    }
}

# -- Option 2: Single-machine fallback --------------------------------
if ($choice -eq "2") {
    Write-Host "  Switching to SINGLE-MACHINE mode..." -ForegroundColor Cyan

    # Patch .env
    $envContent = Get-Content $envFile -Raw
    $patched = $envContent -replace '(?m)^NODE_URLS=.*$', 'NODE_URLS=http://127.0.0.1:8001,http://127.0.0.1:8002,http://127.0.0.1:8003'
    $patched | Set-Content $envFile -NoNewline
    Write-Host "  .env patched -> localhost:8001/8002/8003" -ForegroundColor Green
    Write-Host ""

    # Free ports
    Free-Ports @(8001, 8002, 8003, 3000, 5173)
    Start-Sleep -Seconds 1

    # Start 3 nodes
    Write-Host "  Starting Node 1 on :8001..." -ForegroundColor DarkGray
    Launch "Node 1 :8001" "& '$pythonExe' '$nodePy' --port 8001 --node-id node1"
    Start-Sleep -Milliseconds 500
    Write-Host "  Starting Node 2 on :8002..." -ForegroundColor DarkGray
    Launch "Node 2 :8002" "& '$pythonExe' '$nodePy' --port 8002 --node-id node2"
    Start-Sleep -Milliseconds 500
    Write-Host "  Starting Node 3 on :8003..." -ForegroundColor DarkGray
    Launch "Node 3 :8003" "& '$pythonExe' '$nodePy' --port 8003 --node-id node3"
    Start-Sleep -Seconds 3

    Write-Host ""
    Write-Host "  All 3 nodes started locally." -ForegroundColor Green
}

# -- Option 3: Continue with partial LAN ------------------------------
if ($choice -eq "3") {
    Write-Host "  Proceeding with available nodes (degraded mode)." -ForegroundColor Yellow
}

# -- Option Q: Quit ---------------------------------------------------
if ($choice -eq "Q" -or $choice -eq "q") {
    Write-Host "  Aborted." -ForegroundColor DarkGray
    exit 0
}

# -- Start bridge + frontend (common for options 2 & 3) ---------------
Write-Host ""
Write-Host "  Starting FastAPI bridge on :3000..." -ForegroundColor Cyan
Free-Ports @(3000, 5173)
Start-Sleep -Milliseconds 500

$bridgeCmd = "cd '$bridgeDir'; & '$pythonExe' -m uvicorn main:app --host 0.0.0.0 --port 3000"
Launch "Bridge :3000" $bridgeCmd
Start-Sleep -Seconds 3

Write-Host "  Starting Vite frontend on :5173..." -ForegroundColor Cyan
Launch "Frontend :5173" "cd '$frontDir'; npm run dev"
Start-Sleep -Seconds 3

Write-Host ""
Write-Host "=======================================================" -ForegroundColor Green
Write-Host "                 D-Cloud is LIVE!" -ForegroundColor Green
Write-Host "  Frontend : http://localhost:5173" -ForegroundColor Green
Write-Host "  Bridge   : http://localhost:3000/api/health" -ForegroundColor Green
Write-Host "=======================================================" -ForegroundColor Green
Write-Host ""

Start-Sleep -Seconds 2
Start-Process http://localhost:5173
