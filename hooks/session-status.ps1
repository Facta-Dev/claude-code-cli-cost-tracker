# session-status.ps1 — the Windows (+ pwsh) leg of the cccost session status.
#
# Reads the Claude Code hook event JSON on stdin (the same payload iTerm2's
# hook gets), maintains the same per-session in-flight registry (tools +
# subagents) and shows a Windows toast — no modules: classic NotifyIcon
# balloon via System.Windows.Forms, so plain Windows PowerShell 5.1 runs it
# as-is. Docs: INSTALL.md §3c.

param(
    [switch]$PrintDetail  # dry mode: print the detail line to stdout, no toast
)

$ErrorActionPreference = "SilentlyContinue"

# --- same cache dir as the tracker (shared env override) --------------------
$CacheDir = $env:CC_COST_CACHE_DIR
if (-not $CacheDir) {
    $CacheDir = Join-Path (Join-Path $env:USERPROFILE ".cache") "claude-cost-tracker"
}
# --- per-session in-flight registry (same shape as the python hook) ---------
function Get-Sid([object]$Hook) {
    $m = [regex]::Match("$($Hook.session_id)", "^[A-Za-z0-9_-]+")
    return $m.Value
}
function Get-RegPath([string]$Sid) { return Join-Path $CacheDir "$Sid.procs.json" }
function Read-Registry([string]$Sid) {
    try { return @(Get-Content -Raw (Get-RegPath $Sid) | ConvertFrom-Json) } catch { return @() }
}
function Write-Registry([string]$Sid, [object[]]$Entries) {
    try {
        New-Item -ItemType Directory -Force $CacheDir | Out-Null
        [IO.File]::WriteAllText((Get-RegPath $Sid), (ConvertTo-Json @($Entries) -Compress))
    } catch { }
}
function Get-RunningItem([string]$Event, [object]$Hook) {
    if ($Event -in @("PreToolUse", "PostToolUse")) {
        $tool = "$($Hook.tool_name)".ToLower()
        $i = $Hook.tool_input
        $desc = "$($i.description)$($i.file_path)$($i.command)".Trim()
        $short = ($desc -replace "\s+", " ")
        if ($short.Length -gt 34) { $short = $short.Substring(0, 33) + "..." }
        return "gear $tool`: $short"
    }
    if ($Event -in @("SubagentStart", "SubagentStop")) {
        $a = $Hook.agent
        $agent = if ($a -and "$($a.name)") { "$($a.name)" } else { "$($Hook.agent_name)" }
        if (-not $agent) { $agent = "subagent" }
        return "bot $agent"
    }
    return ""
}
function Update-Registry([string]$Event, [object]$Hook, [string]$Sid) {
    $entries = Read-Registry $Sid
    $item = Get-RunningItem $Event $Hook
    if ($item) {
        $entries = @($entries | Where-Object { $_ -ne $item })
        if ($Event -in @("PreToolUse", "SubagentStart")) { $entries += $item }
    }
    if ($Event -in @("Stop", "SessionEnd", "StopFailure")) { $entries = @() }
    $entries = @($entries | Select-Object -Last 6)
    if ($item -or ($Event -in @("Stop", "SessionEnd", "StopFailure"))) {
        Write-Registry $Sid $entries
    }
    return $entries
}

# --- detail + toast ----------------------------------------------------------
function Get-Cost([string]$Sid) {
    try {
        $c = (Get-Content -Raw (Join-Path $CacheDir "$Sid.json") | ConvertFrom-Json).cost
        return [double]$c.ToString("N2", [Globalization.CultureInfo]::InvariantCulture)
    } catch { return "" }
}
function Build-Detail([string]$Event, [object]$Hook, [object[]]$Entries, [string]$Cost) {
    if ($Event -eq "Notification") {
        $msg = ("$($Hook.message)" -replace "\s+", " ").Trim()
        if ($msg.Length -gt 100) { $msg = $msg.Substring(0, 99) + "..." }
        return "waiting - $msg"
    }
    $parts = @($Entries)
    if ($Cost) { $parts += ("money " + $Cost) }
    $detail = $parts -join " | "
    if ($detail.Length -gt 110) { $detail = $detail.Substring(0, 109) + "..." }
    return $detail
}
function Show-WindowsToast([string]$Title, [string]$Body) {
    try {
        Add-Type -AssemblyName System.Windows.Forms
        $balloon = New-Object System.Windows.Forms.NotifyIcon
        $balloon.Icon = [System.Drawing.SystemIcons]::Information
        $balloon.Visible = $true
        $balloon.ShowBalloonTip(4000, $Title, $Body, [System.Windows.Forms.ToolTipIcon]::Info)
        Start-Sleep -Milliseconds 4500
        $balloon.Dispose()
    } catch { }
}

# --- main ---------------------------------------------------------------------
$hook = $null
try { $hook = ([Console]::In.ReadToEnd() | ConvertFrom-Json) } catch { }
$event = "$($hook.hook_event_name)"
$sid = if ($hook) { Get-Sid $hook } else { "" }
if ($sid) {
    $entries = Update-Registry $event $hook $sid
    $cost = Get-Cost $sid
    $detail = Build-Detail $event $hook $entries $cost
    if ($PrintDetail) { [Console]::Out.WriteLine("DETAIL: $detail") }
    elseif ($detail) { Show-WindowsToast (Split-Path -Leaf (Get-Location)) "cccost $event - $detail" }
}
