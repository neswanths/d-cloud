# ═══════════════════════════════════════════════════════════════════════
#  D-Cloud  —  Node Server Launcher  (run this on EACH node machine)
#  Usage:
#    .\start-node.ps1 -NodeId node1
#    .\start-node.ps1 -NodeId node2
#    .\start-node.ps1 -NodeId node3
#
#  The server binds to 0.0.0.0:8001 so it is reachable from the network.
#  Make sure Windows Firewall allows inbound TCP on port 8001.
# ═══════════════════════════════════════════════════════════════════════

param(
    [Parameter(Mandatory = $true)]
    [ValidateSet("node1", "node2", "node3")]
    [string]$NodeId,

    [int]$Port = 8001,

    [string]$DataDir = $PSScriptRoot
)

$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  D-Cloud Node Server" -ForegroundColor Cyan
Write-Host "═══════════════════════════════════════════════════════" -ForegroundColor Cyan
Write-Host "  Node   : $NodeId"
Write-Host "  Port   : $Port"
Write-Host "  DataDir: $DataDir"
Write-Host ""

# ── Detect Python ────────────────────────────────────────────────────
$python = $null
foreach ($candidate in @("python", "python3", "py")) {
    try {
        $v = & $candidate --version 2>&1
        if ($v -match "Python 3") { $python = $candidate; break }
    }
    catch {}
}

if (-not $python) {
    Write-Host "❌  Python 3 not found. Install from https://python.org" -ForegroundColor Red
    exit 1
}

Write-Host "  Python : $($( & $python --version 2>&1 ))" -ForegroundColor Green

# ── Show LAN IP so user can add it to .env on bridge machine ────────
$lanIp = (Get-NetIPAddress -AddressFamily IPv4 |
    Where-Object { $_.IPAddress -notmatch "^127\." -and $_.PrefixOrigin -ne "WellKnown" } |
    Select-Object -First 1).IPAddress

Write-Host ""
Write-Host "  ✅  This machine's LAN IP: $lanIp" -ForegroundColor Yellow
Write-Host "  Add to bridge .env:  http://${lanIp}:${Port}" -ForegroundColor Yellow
Write-Host ""

# ── Open firewall rule (silent, skip if already exists) ─────────────
$ruleName = "D-Cloud Node $NodeId Port $Port"
$existing = Get-NetFirewallRule -DisplayName $ruleName -ErrorAction SilentlyContinue
if (-not $existing) {
    try {
        New-NetFirewallRule -DisplayName $ruleName `
            -Direction Inbound -Protocol TCP -LocalPort $Port `
            -Action Allow -Profile Any -ErrorAction Stop | Out-Null
        Write-Host "  🔓  Firewall rule created for port $Port" -ForegroundColor Green
    }
    catch {
        Write-Host "  ⚠️   Could not auto-create firewall rule (must run as Admin)" -ForegroundColor Yellow
        Write-Host "      If nodes can't connect, manually allow TCP port $Port in Windows Firewall." -ForegroundColor Yellow
    }
}

Write-Host "  Starting server… (Ctrl+C to stop)" -ForegroundColor Cyan
Write-Host ""

# ── Launch node server ───────────────────────────────────────────────
& $python "$PSScriptRoot\node_server.py" `
    --port $Port `
    --node-id $NodeId `
    --host "0.0.0.0" `
    --data-dir $DataDir
