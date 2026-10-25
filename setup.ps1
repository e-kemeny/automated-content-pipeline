# Export-only setup. Compatible with Windows PowerShell 5.1 and PowerShell 7.
[CmdletBinding()]
param([switch]$CheckOnly, [switch]$SkipSmokeTest, [switch]$InstallMissing)

function Invoke-SetupTool {
    param([string]$File, [string[]]$Arguments)
    try {
        $lines = & $File @Arguments 2>&1
        return @{ Code = $LASTEXITCODE; Text = ($lines | Out-String).Trim() }
    } catch { return @{ Code = 1; Text = $_.Exception.Message } }
}

function Test-SetupPlatform {
    return ([Environment]::OSVersion.Platform -eq 'Win32NT' -and
            $PSVersionTable.PSVersion -ge [version]'5.1')
}

function Get-SetupPython {
    param([string]$File, [string[]]$Prefix = @())
    $probe = 'import json,sys,sysconfig; print(json.dumps(dict(platform=sysconfig.get_platform(), executable=sys.executable, version=list(sys.version_info[:2]), bits=64 if sys.maxsize>2**32 else 32, prefix=sys.prefix, base_prefix=sys.base_prefix)))'
    $result = Invoke-SetupTool $File ($Prefix + @('-I','-B','-S','-c',$probe))
    if ($result.Code -ne 0) { return $null }
    try { $info = $result.Text | ConvertFrom-Json } catch { return $null }
    # Use the locally verified interpreter family, not an untested minimum claim.
    if ($info.version.Count -ne 2 -or $info.version[0] -ne 3 -or
        $info.version[1] -ne 14 -or $info.bits -ne 64 -or $info.platform -ne 'win-amd64') { return $null }
    return $info
}

function Find-SetupPython {
    # Do not execute Store aliases or launchers that may provision Python.
    foreach ($name in @('python','python3')) {
        foreach ($command in @(Get-Command $name -All -CommandType Application -ErrorAction SilentlyContinue)) {
            if ($command.Source -notmatch '[\\/]WindowsApps[\\/]') {
                $info = Get-SetupPython $command.Source
                if ($null -ne $info) { return $info }
            }
        }
    }
    return $null
}

function Test-SetupExecutable {
    param([string]$Name)
    $command = Get-Command $Name -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $command) { return $false }
    $result = Invoke-SetupTool $command.Source @('-version')
    if ($result.Code -ne 0 -or [string]::IsNullOrWhiteSpace($result.Text)) { return $false }
    Write-Host ($result.Text -split "`n")[0]
    return $true
}

function Confirm-SetupChange {
    return ((Read-Host 'Create project-local .venv? Type YES to approve') -ceq 'YES')
}

function New-SetupEnvironment {
    param([string]$Python, [string]$Path)
    # Never repair/delete/overwrite an existing environment, even after a race.
    if (Test-Path -LiteralPath $Path) { throw 'Environment appeared or already exists; refusing creation' }
    $result = Invoke-SetupTool $Python @('-I','-B','-S','-m','venv','--without-pip',$Path)
    if ($result.Code -ne 0) { throw "venv creation failed: $($result.Text)" }
}


function Get-SetupMissing {
    param($Python)
    if ($null -eq $Python) { '64-bit Python 3.14' }
    foreach ($tool in @('ffmpeg','ffprobe')) {
        if (-not (Test-SetupExecutable $tool)) { $tool }
    }
}

function Get-SetupInstallPlan {
    param([string[]]$Missing)
    # IDs verified against microsoft/winget-pkgs; see docs/windows_installer_v2.md.
    if ($Missing -contains '64-bit Python 3.14') {
        @{ Id = 'Python.Python.3.14'; Publisher = 'Python Software Foundation' }
    }
    if ($Missing -contains 'ffmpeg' -or $Missing -contains 'ffprobe') {
        @{ Id = 'Gyan.FFmpeg'; Publisher = 'Gyan (Gyan Doshi)' }
    }
}

function Get-SetupInstallArguments {
    param([string]$Id)
    if ($Id -notin @('Python.Python.3.14','Gyan.FFmpeg')) { throw 'Unapproved package ID' }
    return @('install','--id',$Id,'--exact','--source','winget','--architecture','x64',
             '--scope','user','--no-upgrade','--interactive')
}

function Find-SetupWinGet {
    $command = Get-Command winget -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($command) { return $command.Source }
    return $null
}

function Confirm-SetupSystemInstall {
    return ((Read-Host 'Type YES to approve ONLY the displayed WinGet installations (additional license prompts may follow)') -ceq 'YES')
}

function Invoke-SetupInstallCommand {
    param([string]$File, [string[]]$Arguments)
    # Stream output: source/package agreement prompts must remain visible.
    # No --accept-*-agreements, forced elevation, silent installs or PATH refresh.
    try {
        & $File @Arguments | Out-Host
        return $LASTEXITCODE
    } catch {
        Write-Host $_.Exception.Message
        return 1
    }
}

function Install-SetupMissing {
    param([string[]]$Missing)
    $winget = Find-SetupWinGet
    if (-not $winget) { throw 'WinGet unavailable; install trusted Python/FFmpeg manually (docs/windows_installer_v2.md), reopen PowerShell and rerun CheckOnly' }
    $plan = @(Get-SetupInstallPlan $Missing)
    foreach ($item in $plan) {
        $arguments = Get-SetupInstallArguments $item.Id
        Write-Host "PLAN: $($item.Id); publisher: $($item.Publisher)"
        Write-Host ('COMMAND: "' + $winget + '" ' + ($arguments -join ' '))
    }
    Write-Host 'User-scope only. WinGet/package installers may add USER PATH entries; setup never edits or refreshes PATH.'
    Write-Host 'No upgrades, uninstalls, automatic agreement acceptance or reboots. Missing tools may already be installed but absent from this session PATH.'
    if (-not (Confirm-SetupSystemInstall)) { throw 'System installation declined; WinGet was not invoked' }
    foreach ($item in $plan) {
        $code = Invoke-SetupInstallCommand $winget (Get-SetupInstallArguments $item.Id)
        if ($code -ne 0) {
            throw "WinGet failed/interrupted for $($item.Id) (exit $code). Earlier installations may remain. Review WinGet output; restart if requested, then rerun CheckOnly. No automatic retry or rollback."
        }
        if ($item.Id -eq 'Python.Python.3.14') {
            $available = $null -ne (Find-SetupPython)
        } else {
            $ffmpeg = Test-SetupExecutable 'ffmpeg'
            $ffprobe = Test-SetupExecutable 'ffprobe'
            $available = $ffmpeg -and $ffprobe
        }
        if (-not $available) {
            throw "WinGet returned success for $($item.Id), but verification failed in this session. Open a NEW PowerShell and rerun CheckOnly; PATH was not refreshed. Review installed version/architecture or PATH if still missing. Remaining plan not executed."
        }
        Write-Host "PASS: $($item.Id) available after installation"
    }
}

function Invoke-Setup {
    param([string]$Root, [switch]$CheckOnly, [switch]$SkipSmokeTest, [switch]$InstallMissing)
    $ErrorActionPreference = 'Stop'
    try {
        if ($CheckOnly -and $InstallMissing) { throw '-CheckOnly conflicts with -InstallMissing; no actions performed' }
        if (-not (Test-SetupPlatform)) { throw 'Requires Windows and PowerShell 5.1 or newer' }
        $Root = [IO.Path]::GetFullPath($Root)
        $profile = Join-Path $Root 'requirements-export.txt'
        $requirements = @(Get-Content -LiteralPath $profile | Where-Object {
            $_.Trim() -ne '' -and -not $_.Trim().StartsWith('#')
        })
        if ($requirements.Count -ne 0) {
            throw 'Export package profile changed: requires review before installation; no global or local pip invoked'
        }
        Write-Host 'PASS: export packages: none required (standard library only); no pip needed'
        $venv = Join-Path $Root '.venv'
        $venvPython = Join-Path $venv 'Scripts\python.exe'
        $exists = Test-Path -LiteralPath $venv
        if ($exists) {
            $python = Get-SetupPython $venvPython
            if ($null -eq $python -or $python.prefix -eq $python.base_prefix -or
                [IO.Path]::GetFullPath($python.prefix) -ne $venv -or
                [IO.Path]::GetFullPath($python.executable) -ne $venvPython) {
                throw 'Existing .venv is incomplete/incompatible (requires 64-bit Python 3.14). Preserved; review it manually, then rerun. No automatic repair.'
            }
        } else { $python = Find-SetupPython }
        $missing = @(Get-SetupMissing $python)
        if ($missing.Count) {
            Write-Host ('PLAN: missing or unusable system requirements: ' + ($missing -join ', '))
            if ($InstallMissing) {
                Install-SetupMissing $missing
                if (-not $exists) { $python = Find-SetupPython }
                $missing = @(Get-SetupMissing $python)
                if ($missing.Count) { throw ('Prerequisites still unavailable: ' + ($missing -join ', ')) }
            } else {
                Write-Host 'No system installation or PATH change performed. Use -InstallMissing for approved WinGet installation, or install trusted Python 3.14 x64 and FFmpeg/FFprobe manually.'
                Write-Host 'After installation, open a NEW PowerShell and rerun setup.ps1 -CheckOnly.'
                throw 'System prerequisites unavailable; see docs/windows_installer_v2.md'
            }
        }
        Write-Host "PASS: Python $($python.executable) (64-bit 3.14)"
        if ($exists) { Write-Host 'PLAN: reuse existing .venv; no installation or upgrades' }
        else { Write-Host "PLAN: create $venv with venv --without-pip; no third-party packages" }
        if ($CheckOnly) {
            Write-Host 'PLAN: read-only diagnostics only; smoke test skipped because it creates temporary fixtures'
        } elseif (-not $SkipSmokeTest) {
            Write-Host 'PLAN: diagnostics and synthetic-media smoke test; temporary fixture files will be created and cleaned'
        } else { Write-Host 'PLAN: diagnostics; functional smoke test skipped' }
        if (-not $CheckOnly -and -not $exists) {
            if (-not (Confirm-SetupChange)) { throw 'Installation declined; nothing created' }
            New-SetupEnvironment $python.executable $venv
            $python = Get-SetupPython $venvPython
            if ($null -eq $python -or $python.prefix -eq $python.base_prefix -or
                [IO.Path]::GetFullPath($python.prefix) -ne $venv -or
                [IO.Path]::GetFullPath($python.executable) -ne $venvPython) {
                throw 'New environment validation failed; preserved for manual review, no global fallback'
            }
        }
        # Absolute script paths: never change cwd or rely on activation/global pip.
        $result = Invoke-SetupTool $python.executable @('-B','-S',(Join-Path $Root 'environment_check.py'))
        Write-Host $result.Text
        if ($result.Code -ne 0) { throw 'Environment diagnostics failed' }
        if (-not $CheckOnly -and -not $SkipSmokeTest) {
            # The user must approve temporary file creation even when .venv already exists.
            if ($exists -and (Read-Host 'Run synthetic smoke test (temporary files only)? Type YES to approve') -cne 'YES') {
                throw 'Smoke test declined; use -SkipSmokeTest for diagnostics only'
            }
            $result = Invoke-SetupTool $python.executable @('-B','-S',(Join-Path $Root 'portability_smoke.py'))
            Write-Host $result.Text
            if ($result.Code -ne 0) { throw 'Portability smoke test failed' }
            Write-Host 'PASS: functional smoke test'
        }
        if ($CheckOnly -and -not $exists) {
            throw 'CheckOnly: system prerequisites pass, but project .venv is missing; run setup.ps1 to approve creation'
        }
        Write-Host 'PASS: setup verification (skipped smoke does not establish functional compatibility)'
        return 0
    } catch {
        Write-Host "FAIL: setup: $($_.Exception.Message)"
        return 1
    }
}

if ($MyInvocation.InvocationName -ne '.') {
    exit (Invoke-Setup -Root $PSScriptRoot -CheckOnly:$CheckOnly -SkipSmokeTest:$SkipSmokeTest -InstallMissing:$InstallMissing)
}
