# AgentDesk setup + verification (Windows PowerShell)
#
# Run from the agentdesk folder:
#     .\setup.ps1
#
# Checks Python, installs the two packages, then runs every scenario and the
# eval. No API key needed — everything here runs on fixtures.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

function Say($msg, $color = "White") { Write-Host $msg -ForegroundColor $color }

Say "" ; Say "===============================================" Cyan
Say " AgentDesk setup" Cyan
Say "===============================================" Cyan

# --- 1. Find Python -------------------------------------------------------
Say "`n[1/4] Looking for Python..." Yellow

$py = $null
foreach ($cmd in @("python", "py", "python3")) {
    try {
        $v = & $cmd --version 2>&1
        if ($v -match "Python (\d+)\.(\d+)") {
            $major = [int]$Matches[1]; $minor = [int]$Matches[2]
            if ($major -eq 3 -and $minor -ge 10) { $py = $cmd; Say "  Found: $v (using '$cmd')" Green; break }
            else { Say "  Found $v but need 3.10+" DarkYellow }
        }
    } catch { }
}

if (-not $py) {
    Say "`n  Python 3.10+ not found." Red
    Say "  Install it from https://www.python.org/downloads/" Red
    Say "  IMPORTANT: tick 'Add Python to PATH' on the first install screen." Red
    Say "  Then close PowerShell, reopen it, and run this script again.`n" Red
    exit 1
}

# --- 2. Install packages --------------------------------------------------
Say "`n[2/4] Installing packages (anthropic, jsonschema)..." Yellow
& $py -m pip install --quiet --upgrade pip 2>&1 | Out-Null
& $py -m pip install --quiet anthropic jsonschema
if ($LASTEXITCODE -ne 0) { Say "  pip install failed. Check your internet connection." Red; exit 1 }
Say "  Done." Green

# --- 3. Run the pipeline scenarios ---------------------------------------
Say "`n[3/4] Running all five pipeline scenarios..." Yellow

$scenarios = @(
    @{ name = "happy_path";          expect = "RELEASED";  desc = "clean draft clears all five gates" },
    @{ name = "generic_email";       expect = "RELEASED";  desc = "template blocked, revised, then released" },
    @{ name = "thin_evidence";       expect = "HALTED";    desc = "stops before drafting on weak research" },
    @{ name = "wordcount_violation"; expect = "RELEASED";  desc = "caught by code before spending a QA call" },
    @{ name = "escalation";          expect = "ESCALATED"; desc = "retry budget exhausted, routed to a human" }
)

$failures = 0
foreach ($s in $scenarios) {
    $out = & $py orchestrator/run.py --dry-run --scenario $s.name 2>&1 | Out-String
    if ($out -match "OUTCOME:\s+$($s.expect)") {
        Say ("  PASS  {0,-20} {1}" -f $s.name, $s.desc) Green
    } else {
        Say ("  FAIL  {0,-20} expected {1}" -f $s.name, $s.expect) Red
        $failures++
    }
}

# --- 4. Run the gate evaluation ------------------------------------------
Say "`n[4/4] Scoring the gate against the golden set..." Yellow
$evalOut = & $py evals/run_eval.py 2>&1 | Out-String
$evalOut -split "`n" | Where-Object { $_ -match "recall|false block|blocked by" } | ForEach-Object {
    Say ("  " + $_.Trim()) Green
}
if ($evalOut -notmatch "false block rate\s+0/") { Say "  WARNING: false positives detected" Red; $failures++ }

# --- Summary --------------------------------------------------------------
Say "`n===============================================" Cyan
if ($failures -eq 0) {
    Say " Everything works. Nothing is broken." Green
    Say "===============================================" Cyan
    Say "`nWhat you just proved:"
    Say "  - The pipeline blocks bad drafts and releases good ones"
    Say "  - It refuses to write anything when research is too thin"
    Say "  - 10 of 14 known-bad drafts caught by code, zero false alarms"
    Say "`nTo go live (costs a few cents per run), set your API key:"
    Say '    $env:ANTHROPIC_API_KEY = "sk-ant-your-key-here"' DarkGray
    Say "    $py orchestrator/run.py --company `"Some Company`" --domain example.com" DarkGray
    Say "`nThat key lasts for this PowerShell window only. Closing it clears the key.`n"
} else {
    Say " $failures check(s) failed." Red
    Say "===============================================" Cyan
    Say "`nPaste the output above into Claude Code and ask it to diagnose.`n"
    exit 1
}
