# Spawn parallel Gemini CLI enrichment workers (Windows).
# Each worker uses a unique agent id → no DB row collisions.
#
# Usage:
#   .\run_gemini_workers.ps1              # 5 workers (agent001..agent005)
#   .\run_gemini_workers.ps1 -Count 3
#   .\run_gemini_workers.ps1 -Count 10 -Limit 200   # 200 rows per worker max
#
# Prereqs: gemini on PATH, logged in once (`gemini` interactively)
#          python deps: psycopg2, python-dotenv

param(
    [int]$Count = 5,
    [int]$Limit = 0
)

$Root = $PSScriptRoot
Set-Location $Root

if (-not (Get-Command gemini -ErrorAction SilentlyContinue)) {
    Write-Error "gemini CLI not found. Run: npm install -g @google/gemini-cli"
    exit 1
}

Write-Host "[*] Starting $Count Gemini workers from $Root"

for ($i = 1; $i -le $Count; $i++) {
    $agent = "agent{0:D3}" -f $i
    $args = @("db_gemini_worker.py", "--agent=$agent")
    if ($Limit -gt 0) { $args += "$Limit" }

    Start-Process -FilePath "python" `
        -ArgumentList $args `
        -WorkingDirectory $Root `
        -WindowStyle Normal

    Write-Host "    started $agent (pid in new window)"
    Start-Sleep -Milliseconds 400
}

Write-Host "[+] $Count workers launched. Check each window; monitor:"
Write-Host "    python db_ai_enrich.py --status"
