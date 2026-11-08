<#
Starts Wavefinity from this folder and opens it in the browser.
Silent when all is well. Shows a message box only when something is wrong.

  launch_wavefinity.ps1           normal launch (keeps your saved data)
  launch_wavefinity.ps1 -Clean    also wipes saved data first (test data, generated files)

Use the two .bat files next to this script; they call this one.
#>
param([switch]$Clean)

$ErrorActionPreference = 'Stop'
$App      = $PSScriptRoot
$WfHome   = Join-Path $env:LOCALAPPDATA 'Wavefinity'
$Env      = Join-Path $WfHome 'Env'
$Data     = Join-Path $WfHome 'Data'
$State    = Join-Path $WfHome 'State'
$Port     = 8765
$Url      = "http://127.0.0.1:$Port/"

function Fail([string]$Message) {
    Add-Type -AssemblyName System.Windows.Forms
    [void][System.Windows.Forms.MessageBox]::Show($Message, 'Wavefinity', 'OK', 'Error')
    exit 1
}

function Get-Health {
    try { return Invoke-RestMethod -Uri "${Url}api/health" -TimeoutSec 2 } catch { return $null }
}

function Update-App {
    # Do not prompt in a hidden window or let Git's progress output become a PowerShell error.
    if (-not (Get-Command git -ErrorAction SilentlyContinue)) {
        Fail "Wavefinity could not find Git to check for updates, so it was not started.`nAsk a coder to restore Git."
    }
    $env:GIT_TERMINAL_PROMPT = '0'
    $oldPreference = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $branch = & git -C $App branch --show-current 2>$null
        if ($LASTEXITCODE -ne 0 -or $branch -ne 'main') {
            Fail "Wavefinity was not started because its folder is not on main.`nAsk a coder to restore the launch folder to main."
        }
        $changes = & git -C $App status --porcelain --untracked-files=no 2>$null
        if ($LASTEXITCODE -ne 0 -or $changes) {
            Fail "Wavefinity was not started because its folder has unfinished changes.`nAsk a coder to save or resolve them before launching."
        }
        & git -C $App fetch --quiet --no-tags origin main 2>$null
        if ($LASTEXITCODE -ne 0) {
            Fail "Wavefinity could not check for updates, so it was not started.`nCheck your internet connection and try again."
        }
        & git -C $App merge-base --is-ancestor HEAD FETCH_HEAD 2>$null
        if ($LASTEXITCODE -ne 0) {
            Fail "Wavefinity's local folder differs from the latest version, so it was not started.`nAsk a coder to resolve the folder safely."
        }
        & git -C $App merge --ff-only --quiet FETCH_HEAD 2>$null
        if ($LASTEXITCODE -ne 0) {
            Fail "Wavefinity could not safely update its local folder, so it was not started.`nAsk a coder to resolve the folder safely."
        }
    } finally {
        $ErrorActionPreference = $oldPreference
    }
}

function Stop-Server {
    $listener = Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $listener) { return }
    $health = Get-Health
    if (-not ($health -and $health.ok)) {
        Fail "Something other than Wavefinity is using port $Port, so Wavefinity was not started.`nClose that program and try again."
    }
    Stop-Process -Id $listener.OwningProcess -Force
    for ($i = 0; $i -lt 40 -and (Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue); $i++) {
        Start-Sleep -Milliseconds 250
    }
}

try {
    # Check before stopping the current service or touching saved data.
    Update-App

    # One-time setup: private Python with the packages Wavefinity needs.
    $Python = Join-Path $Env 'Scripts\pythonw.exe'
    if (-not (Test-Path $Python)) {
        Write-Host 'First run: setting up Wavefinity (a few minutes)...'
        & py -3.12 -m venv $Env
        if ($LASTEXITCODE -ne 0) { Fail "Could not create Wavefinity's Python environment.`nInstall Python 3.12 from python.org, then try again." }
        & (Join-Path $Env 'Scripts\python.exe') -m pip install --disable-pip-version-check -r (Join-Path $App 'requirements.txt')
        if ($LASTEXITCODE -ne 0) { Fail "Could not install Wavefinity's packages.`nCheck your internet connection and try again." }
    }

    # Always start fresh so the newest code runs.
    Stop-Server

    if ($Clean -and (Test-Path $Data)) {
        Get-ChildItem -LiteralPath $Data -Force | Remove-Item -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $Data, $State | Out-Null

    $env:WAVEFINITY_DATA_DIR = $Data
    $env:WAVEFINITY_PID_FILE = Join-Path $State 'server.pid'
    $env:PYTHONPATH = ''
    $log = Join-Path $State 'server.log'
    Start-Process -FilePath $Python -WorkingDirectory $App -WindowStyle Hidden `
        -ArgumentList @('wavefinity_web.py', '--no-browser', '--host', '127.0.0.1', '--port', "$Port") `
        -RedirectStandardOutput $log -RedirectStandardError (Join-Path $State 'server.err.log')

    $ready = $false
    for ($i = 0; $i -lt 120; $i++) {
        $h = Get-Health
        if ($h -and $h.ok) { $ready = $true; break }
        Start-Sleep -Milliseconds 500
    }
    if (-not $ready) { Fail "Wavefinity did not start within 60 seconds.`nDetails: $State\server.err.log" }

    # Best-effort: make sure the NN dispatch poller is running (never blocks launch).
    $shim = Join-Path $App 'Start_Wavefinity_Dispatch_Runner_Hidden.vbs'
    if (Test-Path $shim) { try { Start-Process wscript.exe -ArgumentList "`"$shim`"" -WindowStyle Hidden } catch {} }

    Start-Process $Url
}
catch {
    Fail "Wavefinity could not start:`n$($_.Exception.Message)"
}
