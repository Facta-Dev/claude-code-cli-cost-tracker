# install.ps1 — cccost installer for Windows.
#
#   powershell -NoProfile -ExecutionPolicy Bypass -File install.ps1
#
# Runs the test suite, installs the tracker into $HOME\.claude, and prints
# the exact statusLine + hooks JSON to merge (not replace) into
# $HOME\.claude\settings.json. Idempotent — safe to re-run. Mirror of install.sh.

$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

# 1 - tests (python 3.10+ required)
$py = "python"
try { $py = (Get-Command python3, python -ErrorAction SilentlyContinue | Select-Object -First 1).Source } catch { }
if (-not $py) { throw "python 3.10+ required: winget install Python.Python.3.12" }
& $py tests\test_billing.py
if ($LASTEXITCODE -ne 0) { throw "test suite failed - not installing" }

# 2 - layout (same as the mac/linux installer, in $HOME\.claude)
New-Item -ItemType Directory -Force "$HOME\.claude\commands", "$HOME\.claude\hooks" | Out-Null
Copy-Item cccost "$HOME\.claude\cccost" -Recurse -Force
Remove-Item "$HOME\.claude\cccost\__pycache__" -Recurse -Force -ErrorAction SilentlyContinue
Copy-Item statusline.py, cccost.py, prices.json "$HOME\.claude\" -Force
Copy-Item commands\cccost.md "$HOME\.claude\commands\" -Force
Copy-Item hooks\session_status.py, hooks\session-status.ps1 "$HOME\.claude\hooks\" -Force

# 3 - the JSON blocks to merge
Write-Host ""
Write-Host "Installed. Merge (don't replace) into $HOME\.claude\settings.json:"
Write-Host ""
$hook = 'python3 %HOME%\.claude\hooks\session_status.py'.Replace("python3 %HOME%", "python %HOME%")
Write-Host @"
"statusLine": { "type": "command",
  "command": "python %HOME%\\.claude\\statusline.py", "refreshInterval": 5 },
"hooks": { "PreToolUse|PostToolUse|Notification|PermissionRequest|
  SessionStart|SessionEnd|Stop|StopFailure|SubagentStop|UserPromptSubmit": ->
  each event gets  { "type": "command", "command": "$hook" } }
"@
Write-Host ""
Write-Host "A new session shows the live meter; /cccost reports; the toast fires on waiting/done."
