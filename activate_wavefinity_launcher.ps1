<#
.SYNOPSIS
    Installs, upgrades or rolls back the stable Wavefinity launcher on this
    machine (Story 2647). Run it on the local disk AFTER the approved main
    commit has landed - a merge by itself changes nothing on this machine.

.DESCRIPTION
    Activate (default)
        Inspects the real Wavefinity shortcut(s) and the old VBS/BAT chain they
        start, installs a versioned copy of the launcher under
        %LOCALAPPDATA%\Wavefinity\Launcher (independent of every working
        checkout), provisions the managed Python environment, inventories and
        maps the legacy data, preserves the old shortcut and prior launcher,
        atomically retargets only the verified Wavefinity shortcut(s) to the
        stable Launch_Organizer_UI.vbs, then re-reads the result from disk and
        records the evidence. Ambiguous or unsafe state stops it with the
        action to take; it never claims activation it did not observe.
    Promote
        Stages the launcher files from verified approved main as a new version
        and switches the installed launcher to it atomically; rolls back by
        itself if the new version fails its check.
    Rollback
        Switches the installed launcher back to the previous version.
    RestoreShortcut
        Puts the preserved original shortcut(s) back (only where the shortcut
        still points at the stable launcher).

    Run it from the root of a Wavefinity git checkout whose HEAD is on
    origin/main with the launcher files unmodified. It takes the same lock the
    launcher uses, so it waits for - or stops on - a launch in progress.
    It never starts, stops or touches a server unless -VerifyLaunch is given,
    and then only through the installed launcher's own safe path.

.PARAMETER ShortcutPath
    Retarget only this .lnk (it must still pass the identity checks).
.PARAMETER ApprovedCommit
    Require the source checkout's HEAD to be this commit (full or abbreviated).
.PARAMETER VerifyLaunch
    After activation run one real launch (no browser) and print the runtime
    stamp, process record and live health as go-live evidence.
#>
[CmdletBinding()]
param(
    [ValidateSet('Activate', 'Promote', 'Rollback', 'RestoreShortcut')]
    [string]$Action = 'Activate',
    [string]$ShortcutPath,
    [string]$ApprovedCommit,
    [switch]$VerifyLaunch
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'

$ExpectedOrigin = 'https://github.com/happydadto5/Wavefinity.git'
$RuntimeDir = 'C:\Projects\Wavefinity-Runtime'
$SourceRoot = $PSScriptRoot
$Artifacts = @('Launch_Organizer_UI.vbs', 'Launch_Organizer_UI.bat', 'wavefinity_freshness.py')

if (-not $env:LOCALAPPDATA) { throw 'LOCALAPPDATA is not set; run this from a normal Windows user session.' }
$WfHome = Join-Path $env:LOCALAPPDATA 'Wavefinity'
$LauncherRoot = Join-Path $WfHome 'Launcher'
$VersionsDir = Join-Path $LauncherRoot 'versions'
$BackupDir = Join-Path $LauncherRoot 'backup'
$HistoryDir = Join-Path $LauncherRoot 'history'
$EntryVbs = Join-Path $LauncherRoot 'Launch_Organizer_UI.vbs'
$CurrentFile = Join-Path $LauncherRoot 'current.txt'
$PreviousFile = Join-Path $LauncherRoot 'previous.txt'
$StateDir = Join-Path $WfHome 'State'
$DataDir = Join-Path $WfHome 'Data'
$EnvDir = Join-Path $WfHome 'Env'
$EnvPython = Join-Path $EnvDir 'Scripts\python.exe'
$Utf8NoBom = New-Object System.Text.UTF8Encoding($false)
$Shell = New-Object -ComObject WScript.Shell

function Say([string]$Message) { Write-Host "[wavefinity-launcher] $Message" }

function Stop-Activation([string]$Message, [string]$NextStep) {
    throw ($Message + [Environment]::NewLine + '  Action: ' + $NextStep)
}

function Utc-Stamp { (Get-Date).ToUniversalTime().ToString('yyyyMMddTHHmmssZ') }

function Same-Path([string]$A, [string]$B) {
    [string]::Equals([IO.Path]::GetFullPath($A).TrimEnd('\'), [IO.Path]::GetFullPath($B).TrimEnd('\'),
        [StringComparison]::OrdinalIgnoreCase)
}

function Same-Url([string]$A, [string]$B) {
    $clean = { param($u) ($u.Trim().ToLowerInvariant()) -replace '(\.git)?/*$', '' }
    (& $clean $A) -eq (& $clean $B)
}

function Invoke-Git([string]$Dir, [string[]]$GitArgs) {
    $previous = $ErrorActionPreference
    $ErrorActionPreference = 'Continue'
    try {
        $env:GIT_TERMINAL_PROMPT = '0'
        $output = & git -C $Dir @GitArgs 2>$null
        $code = $LASTEXITCODE
    } finally { $ErrorActionPreference = $previous }
    [pscustomobject]@{ Code = $code; Out = (($output | Out-String).Trim()) }
}

function Write-AtomicText([string]$Path, [string]$Text) {
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Path) | Out-Null
    $temp = "$Path.$([guid]::NewGuid().ToString('N')).tmp"
    [IO.File]::WriteAllText($temp, $Text, $Utf8NoBom)
    Publish-File $temp $Path
}

# Move $From over $To atomically (same volume); $From is consumed.
function Publish-File([string]$From, [string]$To) {
    if (Test-Path -LiteralPath $To) {
        [IO.File]::Replace($From, $To, [NullString]::Value)
    } else {
        [IO.File]::Move($From, $To)
    }
}

# ------------------------------------------------------------------ lock
# The same OS byte-range lock wavefinity_freshness.py takes (offset 1,000,000):
# released when its owner dies, never stolen while the owner lives.
function Enter-LaunchLock {
    New-Item -ItemType Directory -Force -Path $StateDir | Out-Null
    $path = Join-Path $StateDir 'launch.lock'
    $deadline = (Get-Date).AddSeconds(120)
    while ($true) {
        $stream = [IO.File]::Open($path, [IO.FileMode]::OpenOrCreate, [IO.FileAccess]::ReadWrite, [IO.FileShare]::ReadWrite)
        $locked = $false
        try { $stream.Lock(1000000, 1); $locked = $true } catch { $locked = $false }
        if ($locked) { break }
        $stream.Dispose()
        if ((Get-Date) -gt $deadline) {
            Stop-Activation 'Another Wavefinity launch or launcher update is in progress.' `
                'Wait for it to finish and run this again. A live lock is never taken over.'
        }
        Start-Sleep -Seconds 1
    }
    $owner = @{ pid = $PID; created = (Get-Process -Id $PID).StartTime.ToUniversalTime().ToString('o')
                role = "activation ($Action)"; started = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ') }
    $bytes = $Utf8NoBom.GetBytes((($owner | ConvertTo-Json -Compress)).PadRight(4096))
    $stream.Position = 0
    $stream.Write($bytes, 0, $bytes.Length)
    $stream.Flush()
    return $stream
}

function Exit-LaunchLock($Stream) {
    if ($Stream) {
        try { $Stream.Unlock(1000000, 1) } catch { }
        $Stream.Dispose()
    }
}

# ------------------------------------------------------------------ source
function Confirm-Source {
    foreach ($name in $Artifacts) {
        if (-not (Test-Path -LiteralPath (Join-Path $SourceRoot $name))) {
            Stop-Activation "Launcher file '$name' is missing from $SourceRoot." `
                'Run this script from the root of an approved Wavefinity checkout.'
        }
    }
    $top = Invoke-Git $SourceRoot @('rev-parse', '--show-toplevel')
    if ($top.Code -ne 0 -or -not (Same-Path $top.Out $SourceRoot)) {
        Stop-Activation "$SourceRoot is not the root of a git checkout." 'Run this script from the root of an approved Wavefinity checkout.'
    }
    $origin = Invoke-Git $SourceRoot @('config', '--get', 'remote.origin.url')
    if ($origin.Code -ne 0 -or -not (Same-Url $origin.Out $ExpectedOrigin)) {
        Stop-Activation "The checkout's origin is '$($origin.Out)', not $ExpectedOrigin." 'Use an approved Wavefinity checkout.'
    }
    $dirty = Invoke-Git $SourceRoot (@('status', '--porcelain', '--') + $Artifacts)
    if ($dirty.Code -ne 0 -or $dirty.Out) {
        Stop-Activation "Launcher files in $SourceRoot differ from the commit:`n$($dirty.Out)" 'Use a clean approved checkout; local edits are never deployed.'
    }
    $head = (Invoke-Git $SourceRoot @('rev-parse', 'HEAD')).Out
    $fetch = Invoke-Git $SourceRoot @('fetch', '--quiet', $ExpectedOrigin, 'main')
    if ($fetch.Code -ne 0) {
        Stop-Activation 'GitHub could not be reached, so the source cannot be verified as approved main.' 'Connect to the internet and run this again.'
    }
    $tip = (Invoke-Git $SourceRoot @('rev-parse', 'FETCH_HEAD')).Out
    if ((Invoke-Git $SourceRoot @('merge-base', '--is-ancestor', 'HEAD', $tip)).Code -ne 0) {
        Stop-Activation "Checkout HEAD $head is not part of origin/main." 'Deploy only from an approved main commit.'
    }
    if ($ApprovedCommit -and -not $head.StartsWith($ApprovedCommit.Trim().ToLowerInvariant())) {
        Stop-Activation "Checkout HEAD $head is not the approved commit $ApprovedCommit." 'Check out the approved commit and run this again.'
    }
    [pscustomobject]@{ Commit = $head; MainTip = $tip }
}

# ------------------------------------------------------------------ shortcuts
function Get-LauncherScript([string]$Target, [string]$Arguments) {
    $pattern = '(?i)([A-Za-z]:\\[^"<>|?*]*?Launch_Organizer_UI\.(?:vbs|bat))'
    foreach ($text in @($Target, $Arguments)) {
        if ($text -and ($text -match $pattern)) { return $Matches[1] }
    }
    return $null
}

function Get-ShortcutKind([string]$Script) {
    if (Same-Path $Script $EntryVbs) { return 'stable' }
    $dir = Split-Path -Parent $Script
    if ((Test-Path -LiteralPath $Script) -and (Test-Path -LiteralPath (Join-Path $dir 'wavefinity_web.py')) -and
        (Test-Path -LiteralPath (Join-Path $dir 'wavefinity_freshness.py'))) { return 'legacy' }
    return 'unverified'
}

function Find-WavefinityShortcuts {
    $roots = @()
    foreach ($name in 'Desktop', 'CommonDesktopDirectory', 'Programs', 'CommonPrograms', 'Startup', 'CommonStartup') {
        $folder = [Environment]::GetFolderPath($name)
        if ($folder -and (Test-Path -LiteralPath $folder)) { $roots += $folder }
    }
    $pinned = Join-Path $env:APPDATA 'Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar'
    if (Test-Path -LiteralPath $pinned) { $roots += $pinned }
    $seen = @{}
    $found = @()
    foreach ($root in ($roots | Select-Object -Unique)) {
        foreach ($file in @(Get-ChildItem -LiteralPath $root -Recurse -Filter '*.lnk' -File -ErrorAction SilentlyContinue)) {
            if ($seen.ContainsKey($file.FullName.ToLowerInvariant())) { continue }
            $seen[$file.FullName.ToLowerInvariant()] = $true
            try { $link = $Shell.CreateShortcut($file.FullName) } catch { continue }
            $script = Get-LauncherScript $link.TargetPath $link.Arguments
            if (-not $script) { continue }
            $found += [pscustomobject]@{
                Path = $file.FullName; Target = $link.TargetPath; Arguments = $link.Arguments
                WorkingDirectory = $link.WorkingDirectory; Script = $script; Kind = (Get-ShortcutKind $script)
            }
        }
    }
    return , $found
}

function Select-Shortcuts {
    $all = Find-WavefinityShortcuts
    foreach ($one in $all) { Say "Found shortcut: $($one.Path) -> $($one.Target) $($one.Arguments) [$($one.Kind)]" }
    $usable = @($all | Where-Object { $_.Kind -ne 'unverified' })
    $unverified = @($all | Where-Object { $_.Kind -eq 'unverified' })
    if ($ShortcutPath) {
        $usable = @($usable | Where-Object { Same-Path $_.Path $ShortcutPath })
        if ($usable.Count -ne 1) {
            Stop-Activation "-ShortcutPath $ShortcutPath is not a verified Wavefinity shortcut." 'Pass the .lnk that starts your Wavefinity checkout.'
        }
    }
    if ($usable.Count -eq 0) {
        $note = if ($unverified.Count) { ' Shortcuts naming Launch_Organizer_UI whose folder is not a Wavefinity checkout were left alone: ' + (($unverified | ForEach-Object { $_.Path }) -join '; ') } else { '' }
        Stop-Activation ('No shortcut that starts a Wavefinity launcher was found.' + $note) 'Pass -ShortcutPath <the .lnk you use to start Wavefinity>.'
    }
    foreach ($one in $usable) {
        $item = Get-Item -LiteralPath $one.Path -Force
        if ($item.IsReadOnly) { Stop-Activation "$($one.Path) is read-only." 'Clear the read-only flag or pass a different -ShortcutPath.' }
        $probe = Join-Path (Split-Path -Parent $one.Path) (".wf-probe-" + [guid]::NewGuid().ToString('N'))
        try { New-Item -ItemType File -Path $probe | Out-Null; Remove-Item -LiteralPath $probe -Force }
        catch { Stop-Activation "The folder holding $($one.Path) is not writable, so it cannot be retargeted safely." 'Run as a user who can modify that shortcut, or pass a different -ShortcutPath.' }
    }
    return , $usable
}

function Set-ShortcutFile([string]$Link, [string]$FromFile, [string]$NewTarget) {
    $temp = Join-Path (Split-Path -Parent $Link) ('.wf-' + [guid]::NewGuid().ToString('N') + '.lnk')
    Copy-Item -LiteralPath $FromFile -Destination $temp
    try {
        if ($NewTarget) {
            $edit = $Shell.CreateShortcut($temp)
            $edit.TargetPath = $NewTarget
            $edit.Arguments = ''
            $edit.WorkingDirectory = $LauncherRoot
            $edit.Save()
        }
        [IO.File]::Replace($temp, $Link, [NullString]::Value)
    } finally {
        if (Test-Path -LiteralPath $temp) { Remove-Item -LiteralPath $temp -Force }
    }
}

# ------------------------------------------------------------------ environment and data
function Initialize-Environment {
    if (-not (Test-Path -LiteralPath $EnvPython)) {
        $base = $null
        foreach ($candidate in @(@{ Name = 'py'; Prefix = @('-3') }, @{ Name = 'python'; Prefix = @() })) {
            $command = Get-Command $candidate.Name -ErrorAction SilentlyContinue | Select-Object -First 1
            if (-not $command) { continue }
            $probe = & $command.Source @($candidate.Prefix + @('-c', 'import sys, venv; print(sys.version_info[0])')) 2>$null
            if ($LASTEXITCODE -eq 0 -and "$probe".Trim() -eq '3') { $base = @{ Exe = $command.Source; Prefix = $candidate.Prefix }; break }
        }
        if (-not $base) { Stop-Activation 'No Python 3 with the venv module was found.' 'Install Python 3 from python.org, then run this again.' }
        Say "Creating the managed Python environment at $EnvDir"
        New-Item -ItemType Directory -Force -Path $WfHome | Out-Null
        & $base.Exe @($base.Prefix + @('-m', 'venv', $EnvDir))
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $EnvPython)) {
            Stop-Activation 'The managed Python environment could not be created.' 'Fix the error above and run this again.'
        }
    }
    & $EnvPython (Join-Path $SourceRoot 'wavefinity_freshness.py') --ensure-dependencies
    if ($LASTEXITCODE -ne 0) {
        Stop-Activation 'The pinned Wavefinity dependencies could not be installed.' 'Fix the error above (network, disk) and run this again.'
    }
}

function Initialize-DataMapping([string[]]$LegacyDirs) {
    New-Item -ItemType Directory -Force -Path $DataDir | Out-Null
    $mapPath = Join-Path $DataDir 'data-map.json'
    # Re-activating with nothing legacy left to inventory must not erase the earlier inventory.
    if ((-not $LegacyDirs) -and (Test-Path -LiteralPath $mapPath)) { return $mapPath }
    $items = @()
    foreach ($dir in ($LegacyDirs | Select-Object -Unique)) {
        foreach ($name in 'generated', 'wavefinity_prefs.json', '.venv', 'wavefinity.pid', 'wavefinity_server.log') {
            $path = Join-Path $dir $name
            if (-not (Test-Path -LiteralPath $path)) { $items += [ordered]@{ legacy_path = $path; exists = $false }; continue }
            $isFolder = (Get-Item -LiteralPath $path -Force).PSIsContainer
            $files = if ($isFolder) { @(Get-ChildItem -LiteralPath $path -Recurse -File -Force -ErrorAction SilentlyContinue) } else { @(Get-Item -LiteralPath $path -Force) }
            $size = [long](($files | Measure-Object -Property Length -Sum).Sum)
            $entry = [ordered]@{ legacy_path = $path; exists = $true; files = $files.Count; bytes = $size }
            if ($name -eq 'generated') {
                $target = Join-Path $DataDir 'generated'
                New-Item -ItemType Directory -Force -Path $target | Out-Null
                # Copy only files the target lacks; nothing is overwritten and the legacy folder is not modified.
                & robocopy $path $target /E /XC /XN /XO /R:1 /W:1 /NFL /NDL /NJH /NJS /NP | Out-Null
                if ($LASTEXITCODE -ge 8) {
                    Stop-Activation "Legacy generated output at $path could not be mapped (robocopy exit $LASTEXITCODE)." 'Free disk space or fix access, then run this again. Nothing was retargeted.'
                }
                $entry.mapped_to = $target; $entry.action = 'copied without overwriting; original left in place'
            } elseif ($name -eq 'wavefinity_prefs.json') {
                $target = Join-Path $DataDir 'wavefinity_prefs.json'
                if (-not (Test-Path -LiteralPath $target)) { Copy-Item -LiteralPath $path -Destination $target }
                $entry.mapped_to = $target; $entry.action = 'copied if absent; original left in place'
            } elseif ($name -eq '.venv') {
                $entry.action = 'not migrated (a virtual environment cannot be relocated); replaced by the managed environment at ' + $EnvDir
            } else {
                $entry.action = 'left in place; regenerated by the launcher under ' + $StateDir
            }
            $items += $entry
        }
    }
    $map = [ordered]@{
        created_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ')
        runtime_dir = $RuntimeDir
        runtime_data_dir = $DataDir
        managed_python_environment = $EnvDir
        process_state_dir = $StateDir
        user_preferences_dir = (Join-Path $env:APPDATA 'Wavefinity')
        legacy_checkouts = @($LegacyDirs | Select-Object -Unique)
        items = $items
    }
    Write-AtomicText $mapPath ($map | ConvertTo-Json -Depth 6)
    return $mapPath
}

# ------------------------------------------------------------------ launcher versions
function Install-LauncherVersion($Source) {
    $id = '{0}-{1}' -f (Utc-Stamp), $Source.Commit.Substring(0, 12)
    New-Item -ItemType Directory -Force -Path $VersionsDir | Out-Null
    $final = Join-Path $VersionsDir $id
    if (Test-Path -LiteralPath $final) { Stop-Activation "Launcher version $id already exists." 'Run this again in a moment.' }
    $temp = Join-Path $VersionsDir ('.staging-' + [guid]::NewGuid().ToString('N'))
    New-Item -ItemType Directory -Path $temp | Out-Null
    $hashes = [ordered]@{}
    foreach ($name in $Artifacts) {
        $from = Join-Path $SourceRoot $name
        $to = Join-Path $temp $name
        if ($name -like '*.py') {
            Copy-Item -LiteralPath $from -Destination $to
        } else {
            $text = ([IO.File]::ReadAllText($from)) -replace "`r?`n", "`r`n"   # batch and script files need CRLF
            [IO.File]::WriteAllText($to, $text, $Utf8NoBom)
        }
        $hashes[$name] = (Get-FileHash -LiteralPath $to -Algorithm SHA256).Hash
    }
    $info = [ordered]@{
        version = $id; source_commit = $Source.Commit; approved_main_tip = $Source.MainTip
        installed_utc = (Get-Date).ToUniversalTime().ToString('yyyy-MM-ddTHH:mm:ssZ'); source_root = $SourceRoot; sha256 = $hashes
    }
    [IO.File]::WriteAllText((Join-Path $temp 'launcher.json'), ($info | ConvertTo-Json -Depth 4), $Utf8NoBom)
    Move-Item -LiteralPath $temp -Destination $final
    & $EnvPython (Join-Path $final 'wavefinity_freshness.py') --self-check
    if ($LASTEXITCODE -ne 0) {
        Stop-Activation "Staged launcher $id failed its self-check, so it was not promoted." "It is kept at $final for inspection; the installed launcher is unchanged."
    }
    return $id
}

# Promote a staged version: the entry VBS and current.txt are each replaced atomically.
function Set-CurrentVersion([string]$Id) {
    $dir = Join-Path $VersionsDir $Id
    if (-not (Test-Path -LiteralPath (Join-Path $dir 'launcher.json'))) { Stop-Activation "Launcher version $Id is not installed." 'Run -Action Promote from approved main.' }
    $previous = $null
    if (Test-Path -LiteralPath $CurrentFile) { $previous = ([IO.File]::ReadAllText($CurrentFile)).Trim() }
    New-Item -ItemType Directory -Force -Path $LauncherRoot | Out-Null
    $temp = "$EntryVbs.$([guid]::NewGuid().ToString('N')).tmp"
    Copy-Item -LiteralPath (Join-Path $dir 'Launch_Organizer_UI.vbs') -Destination $temp
    Publish-File $temp $EntryVbs
    if ($previous -and $previous -ne $Id) { Write-AtomicText $PreviousFile $previous }
    Write-AtomicText $CurrentFile $Id
    return $previous
}

function Save-History([string]$Path, $Record) {
    New-Item -ItemType Directory -Force -Path $HistoryDir | Out-Null
    Write-AtomicText $Path ($Record | ConvertTo-Json -Depth 6)
}

function Show-Evidence($Shortcuts, [string]$HistoryFile, [string]$MapFile) {
    Say '---- OBSERVED STATE (re-read from disk) ----'
    foreach ($one in $Shortcuts) {
        $now = $Shell.CreateShortcut($one.Path)
        Say "Shortcut: $($one.Path)"
        Say "  target now : $($now.TargetPath)"
        if ($one.PSObject.Properties['Backup']) { Say "  old target : $($one.Target) $($one.Arguments)  (original .lnk preserved at $($one.Backup))" }
    }
    $installed = if (Test-Path -LiteralPath $CurrentFile) { ([IO.File]::ReadAllText($CurrentFile)).Trim() } else { '(none)' }
    Say "Installed launcher version (current.txt): $installed"
    if (Test-Path -LiteralPath $PreviousFile) { Say "Previous launcher version (rollback): $(([IO.File]::ReadAllText($PreviousFile)).Trim())" }
    if ($HistoryFile) { Say "Deployment record: $HistoryFile" }
    if ($MapFile) { Say "Data inventory and mapping: $MapFile" }
    $stamp = Join-Path $RuntimeDir '.git\wavefinity-build-stamp.json'
    if (Test-Path -LiteralPath $stamp) { Say "Runtime stamp: $([IO.File]::ReadAllText($stamp) -replace '\s+', ' ')" }
    else { Say 'Runtime stamp: none yet - the runtime checkout is created by the next launch (or -VerifyLaunch).' }
    Say "Rollback: run this script with -Action Rollback (launcher version) or -Action RestoreShortcut (original shortcut)."
}

# ------------------------------------------------------------------ actions
function Invoke-Activate {
    $source = Confirm-Source
    $shortcuts = Select-Shortcuts
    Initialize-Environment
    $legacy = @($shortcuts | Where-Object { $_.Kind -eq 'legacy' } | ForEach-Object { Split-Path -Parent $_.Script })
    $mapFile = Initialize-DataMapping $legacy
    $id = Install-LauncherVersion $source
    $stamp = Utc-Stamp
    $historyFile = Join-Path $HistoryDir "$stamp-activate.json"
    $record = [ordered]@{
        action = 'activate'; status = 'in-progress'; utc = $stamp; source_commit = $source.Commit
        launcher_version = $id; stable_launcher = $EntryVbs; data_map = $mapFile; shortcuts = @()
    }
    Save-History $historyFile $record
    $previousVersion = Set-CurrentVersion $id
    $record.previous_launcher_version = $previousVersion
    $applied = @()
    try {
        New-Item -ItemType Directory -Force -Path $BackupDir | Out-Null
        foreach ($one in $shortcuts) {
            if ($one.Kind -eq 'stable') { Say "Already points at the stable launcher: $($one.Path)"; continue }
            $backup = Join-Path $BackupDir ("$stamp-" + (Split-Path -Leaf $one.Path))
            Copy-Item -LiteralPath $one.Path -Destination $backup
            $one | Add-Member -NotePropertyName Backup -NotePropertyValue $backup
            $applied += $one
            Set-ShortcutFile $one.Path $one.Path $EntryVbs
            $check = $Shell.CreateShortcut($one.Path)
            if (-not (Same-Path $check.TargetPath $EntryVbs)) { throw "Shortcut $($one.Path) reads back as '$($check.TargetPath)', not the stable launcher." }
            $record.shortcuts += [ordered]@{ path = $one.Path; old_target = $one.Target; old_arguments = $one.Arguments
                old_working_directory = $one.WorkingDirectory; backup = $backup; new_target = $check.TargetPath }
        }
    } catch {
        $failure = $_.Exception.Message
        foreach ($one in $applied) { try { Set-ShortcutFile $one.Path $one.Backup $null } catch { Say "COULD NOT RESTORE $($one.Path); the original is at $($one.Backup)" } }
        $record.status = 'failed: ' + $failure
        Save-History $historyFile $record
        throw
    }
    $record.status = 'activated'
    Save-History $historyFile $record
    Add-Content -LiteralPath (Join-Path $LauncherRoot 'activation-log.jsonl') -Value ($record | ConvertTo-Json -Depth 6 -Compress)
    Show-Evidence $shortcuts $historyFile $mapFile
    Say 'ACTIVATED: the next normal launch uses the stable launcher.'
}

function Invoke-Promote {
    if (-not (Test-Path -LiteralPath $CurrentFile)) {
        Stop-Activation 'The stable launcher is not installed yet, so there is nothing to promote.' 'Run this script without -Action (Activate) first.'
    }
    $source = Confirm-Source
    Initialize-Environment
    $id = Install-LauncherVersion $source
    $previousVersion = Set-CurrentVersion $id
    $installed = ([IO.File]::ReadAllText($CurrentFile)).Trim()
    & $EnvPython (Join-Path (Join-Path $VersionsDir $installed) 'wavefinity_freshness.py') --self-check
    if ($installed -ne $id -or $LASTEXITCODE -ne 0) {
        if ($previousVersion) { Set-CurrentVersion $previousVersion | Out-Null }
        Stop-Activation "Promoted launcher $id did not verify; the previous version $previousVersion was restored." 'Check the output above.'
    }
    $stamp = Utc-Stamp
    $record = [ordered]@{ action = 'promote'; status = 'promoted'; utc = $stamp; source_commit = $source.Commit
        launcher_version = $id; previous_launcher_version = $previousVersion }
    $historyFile = Join-Path $HistoryDir "$stamp-promote.json"
    Save-History $historyFile $record
    Add-Content -LiteralPath (Join-Path $LauncherRoot 'activation-log.jsonl') -Value ($record | ConvertTo-Json -Compress)
    $stable = @(Find-WavefinityShortcuts | Where-Object { $_.Kind -eq 'stable' })
    if ($stable.Count -eq 0) { Say 'WARNING: no shortcut points at the stable launcher yet; run Activate to retarget one.' }
    Show-Evidence $stable $historyFile $null
    Say "PROMOTED launcher $id (previous: $previousVersion)."
}

function Invoke-Rollback {
    if (-not (Test-Path -LiteralPath $PreviousFile)) { Stop-Activation 'There is no previous launcher version recorded.' 'Nothing to roll back to.' }
    $target = ([IO.File]::ReadAllText($PreviousFile)).Trim()
    New-Item -ItemType Directory -Force -Path $WfHome | Out-Null
    if (-not (Test-Path -LiteralPath $EnvPython)) { Stop-Activation 'The managed Python environment is missing.' 'Run Activate to rebuild it.' }
    & $EnvPython (Join-Path (Join-Path $VersionsDir $target) 'wavefinity_freshness.py') --self-check
    if ($LASTEXITCODE -ne 0) { Stop-Activation "Previous launcher $target failed its self-check." 'It was not switched to.' }
    $replaced = Set-CurrentVersion $target
    $stamp = Utc-Stamp
    Save-History (Join-Path $HistoryDir "$stamp-rollback.json") ([ordered]@{ action = 'rollback'; utc = $stamp; launcher_version = $target; replaced_launcher_version = $replaced })
    Show-Evidence @() $null $null
    Say "ROLLED BACK to launcher $target (replaced: $replaced)."
}

function Invoke-RestoreShortcut {
    $latest = $null
    $record = $null
    foreach ($file in @(Get-ChildItem -LiteralPath $HistoryDir -Filter '*-activate.json' -File -ErrorAction SilentlyContinue | Sort-Object Name -Descending)) {
        $candidate = Get-Content -LiteralPath $file.FullName -Raw | ConvertFrom-Json
        if ($candidate.status -eq 'activated' -and @($candidate.shortcuts).Count -gt 0) { $latest = $file; $record = $candidate; break }
    }
    if (-not $latest) { Stop-Activation 'No activation record that changed a shortcut was found.' 'Nothing to restore.' }
    $restored = @()
    foreach ($one in @($record.shortcuts)) {
        if ($ShortcutPath -and -not (Same-Path $one.path $ShortcutPath)) { continue }
        $now = $Shell.CreateShortcut($one.path)
        if (-not (Same-Path $now.TargetPath $EntryVbs)) {
            Stop-Activation "$($one.path) no longer points at the stable launcher (it is '$($now.TargetPath)'), so it was not overwritten." 'Restore it by hand from the preserved copy if you still want the original.'
        }
        if (-not (Test-Path -LiteralPath $one.backup)) { Stop-Activation "The preserved shortcut $($one.backup) is missing." 'Recreate the shortcut by hand.' }
        Set-ShortcutFile $one.path $one.backup $null
        $restored += [pscustomobject]@{ Path = $one.path; Target = $one.old_target; Arguments = $one.old_arguments }
    }
    if ($restored.Count -eq 0) { Stop-Activation 'No matching shortcut was recorded in the latest activation.' 'Nothing to restore.' }
    Show-Evidence $restored $latest.FullName $null
    Say 'RESTORED the original shortcut(s); the stable launcher stays installed.'
}

function Invoke-VerifyLaunch {
    $installed = ([IO.File]::ReadAllText($CurrentFile)).Trim()
    $statusFile = Join-Path $env:TEMP ('wf-verify-' + [guid]::NewGuid().ToString('N') + '.txt')
    $env:WAVEFINITY_STATUS_FILE = $statusFile
    try { & $EnvPython (Join-Path (Join-Path $VersionsDir $installed) 'wavefinity_freshness.py') --launch --no-browser; $code = $LASTEXITCODE }
    finally { Remove-Item Env:WAVEFINITY_STATUS_FILE -ErrorAction SilentlyContinue }
    if (Test-Path -LiteralPath $statusFile) { Say ('Launch outcome: ' + ((Get-Content -LiteralPath $statusFile) -join ' | ')); Remove-Item -LiteralPath $statusFile -Force }
    $instance = Join-Path $StateDir 'instance.json'
    if (Test-Path -LiteralPath $instance) { Say ('Process record: ' + ([IO.File]::ReadAllText($instance) -replace '\s+', ' ')) }
    $client = New-Object System.Net.WebClient
    $client.Proxy = $null
    try { Say ('Live health: ' + $client.DownloadString('http://127.0.0.1:8765/api/health')) } catch { Say "Live health: unavailable ($($_.Exception.Message))" }
    if ($code -ne 0) { Stop-Activation 'The live verification launch did not reach READY.' 'Read the launch outcome above; the launcher itself stays installed.' }
}

# ------------------------------------------------------------------ main
$lock = $null
try {
    $lock = Enter-LaunchLock
    switch ($Action) {
        'Activate' { Invoke-Activate }
        'Promote' { Invoke-Promote }
        'Rollback' { Invoke-Rollback }
        'RestoreShortcut' { Invoke-RestoreShortcut }
    }
} catch {
    Exit-LaunchLock $lock
    $lock = $null
    Write-Host ''
    Write-Host "[wavefinity-launcher] NOT COMPLETED ($Action): $($_.Exception.Message)" -ForegroundColor Red
    Write-Host '[wavefinity-launcher] Nothing is claimed as activated beyond what is listed above as observed.' -ForegroundColor Red
    exit 2
} finally {
    Exit-LaunchLock $lock
}

if ($VerifyLaunch -and $Action -in @('Activate', 'Promote')) {
    try { Invoke-VerifyLaunch } catch {
        Write-Host "[wavefinity-launcher] LIVE VERIFICATION FAILED: $($_.Exception.Message)" -ForegroundColor Red
        exit 2
    }
}
exit 0
