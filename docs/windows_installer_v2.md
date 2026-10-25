# Windows installer V2: approved system installation

V2 extends [V1](windows_installer_v1.md); export algorithms and dependencies are
unchanged. Use Windows PowerShell 5.1+ from any cwd. Repository paths resolve
from setup.ps1, not the caller's directory.

## Commands and fresh-machine bootstrap

```powershell
.\setup.ps1 -CheckOnly
.\setup.ps1 -InstallMissing
.\setup.ps1 -InstallMissing -SkipSmokeTest
.\setup.ps1
.\setup.ps1 -SkipSmokeTest
```

Clone the repository on the destination computer. Python is not required to
start the PowerShell script. CheckOnly reports each unavailable dependency.
If Python 3.14 x64 or FFmpeg/FFprobe is unavailable, InstallMissing builds an
exact WinGet plan and requires literal `YES` before invoking it. The flag itself
is not approval. Both missing FFmpeg tools map to a single package installation.

Default mode preserves V1 guided system installation and approval-gated local
venv creation. CheckOnly never invokes WinGet, prompts, downloads, creates a venv,
or runs the file-producing smoke test. CheckOnly plus InstallMissing is rejected.
SkipSmokeTest skips only functional verification; diagnostics still run and other
approved setup actions can occur.

## Verified package identities

Verified on 2026-10-25 against Microsoft's community WinGet manifest repository:

| Dependency | Exact ID | Publisher / download origin |
|---|---|---|
| Python 3.14 x64 | Python.Python.3.14 | Python Software Foundation; python.org |
| FFmpeg + FFprobe | Gyan.FFmpeg | Gyan / Gyan Doshi; GyanD/codexffmpeg releases |

Evidence: [Python x64/user installer manifest](https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/p/Python/Python/3/14/3.14.0/Python.Python.3.14.installer.yaml),
[Python signing publisher](https://www.python.org/downloads/?keys=Python+3+Windows+10+installer),
[FFmpeg manifest including FFprobe](https://raw.githubusercontent.com/microsoft/winget-pkgs/master/manifests/g/Gyan/FFmpeg/9.0/Gyan.FFmpeg.installer.yaml),
and [Gyan publisher metadata](https://github.com/microsoft/winget-pkgs/blob/master/manifests/g/Gyan/FFmpeg/9.0/Gyan.FFmpeg.locale.en-US.yaml).
These are identity references, not new dependency pins. WinGet selects its current
version for each exact ID; Python's ID limits the family to 3.14. New patch/tool
versions are not claimed verified. Record what the destination actually installs.

The displayed commands are:

```powershell
winget install --id Python.Python.3.14 --exact --source winget --architecture x64 --scope user --no-upgrade --interactive
winget install --id Gyan.FFmpeg --exact --source winget --architecture x64 --scope user --no-upgrade --interactive
```

Only needed packages are included. No broad searches, upgrade-all, forced
replacement, uninstallation, machine scope or automatic reboot. The installer
uses an allowlist and leaves WinGet hash checks enabled. See Microsoft's
[install option reference](https://learn.microsoft.com/en-us/windows/package-manager/winget/install).
The configured `winget` source must be the trusted Microsoft community source;
setup does not repair or replace local source configuration.

## Approval and PATH behavior

Before executing the plan, setup displays package IDs, publishers, executable
path and exact arguments. Output streams immediately so WinGet source/package
agreement prompts remain visible. Neither agreement auto-accept flag is passed.
The user must separately accept terms if WinGet requests them. An unattended or
noninteractive run without consent fails; there is no bypass flag.

Setup never assigns process PATH or edits user/machine PATH. Approved WinGet or
vendor installers may register **user** PATH entries (the verified Python user
manifest uses PrependPath). This effect is disclosed before approval. There is
no self-elevation or machine-scope fallback. Reject unexpected elevation requests
and investigate configuration rather than retrying as administrator automatically.

After each successful WinGet exit, setup probes the dependency again. Python
must report 3.14, 64 bits and win-amd64; FFmpeg and FFprobe must each execute
-version successfully. Zero installer exit alone is not success. If discovery
still fails, setup stops before venv creation or the remaining installation plan.
Open a NEW PowerShell (or restart the terminal host if it retains stale PATH),
then run CheckOnly. Do not repeatedly approve installs to fix a stale session.
No explicit PATH refresh or automatic reboot occurs.

## Recovery and manual fallback

- WinGet absent: setup stops with manual guidance; it does not install WinGet.
  Obtain [App Installer](https://learn.microsoft.com/en-us/windows/package-manager/winget/)
  through the normal Windows process, or manually install trusted dependencies.
- Manual Python: use the [official Python 3.14 release](https://www.python.org/downloads/release/python-3140/)
  Windows x64 installer; explicitly review user-scope/PATH options. Other 3.14
  patch releases require their own validation. Do not remove other Python versions.
- Manual media tools: use [Gyan's builds](https://www.gyan.dev/ffmpeg/builds/)
  including FFmpeg and FFprobe, and explicitly configure their bin path yourself.
- A source/terms/network failure, cancellation or nonzero installer exit stops
  setup. Review WinGet's visible output. Earlier successful packages remain;
  there is no rollback, deletion or automatic retry. Rerun CheckOnly first.
- Working prerequisites are not reinstalled; --no-upgrade also prevents changing
  an already registered package merely because PATH discovery failed. This can
  leave an incompatible existing package unresolved: diagnose it manually.
- Compatible .venv is reused; incompatible/partial .venv is preserved and blocks
  system installation before any action. No automatic environment repair occurs.

Only after all prerequisites pass can setup request the separate approval for
project .venv creation. The export profile is still empty: no pip, ML weights,
CUDA, transcription or inference installs. Venv creation uses --without-pip.
Diagnostics and optional synthetic smoke retain the V1 behavior.

## Validation and limits

Run on the second computer, record Python/PowerShell/FFmpeg versions and commit:

```powershell
.\setup.ps1 -CheckOnly
.\setup.ps1 -InstallMissing
# If setup requests restart, reopen PowerShell and repeat CheckOnly first.
.\.venv\Scripts\python.exe verify.py
.\.venv\Scripts\python.exe -B -S portability_smoke.py
```

Local installation tests mock every installation command; no WinGet install,
global pip, or real .venv creation was performed. Real CheckOnly is read-only;
missing .venv yields exit 1 even when system prerequisites pass. Synthetic smoke
encodes disposable fixtures only, with explicit user authorization for this
milestone. Production caches are validated read-only. Real downloads/installation,
source-agreement interaction, reboot handling and RTX 4090/second-computer
compatibility remain unverified. Older WinGet builds lacking required flags fail
rather than retrying with weaker options. No minimum WinGet version is invented.

## Line endings

core.autocrlf was false; the V1 installer, test and guide were tracked as CRLF.
.gitattributes now applies LF to only the installer/test/README and installer
Markdown guides touched here. LF PowerShell scripts are supported by both tested
shells. Other existing files and binary/media attributes remain untouched; extend
this incremental policy when deliberately editing other files. No repository-wide
renormalization or Git configuration change was performed.

Recorded local results (2026-10-25): baseline 352 passed / 1 deferred; final
364 passed / 1 deferred, plus four motion checks. All 25 installer tests passed
with installation mocked. Real CheckOnly in PowerShell 7.6.5 and Windows
PowerShell 5.1.26100.9711 detected the system prerequisites and returned the
expected exit 1 for missing .venv, including from outside the repository cwd.
No real installation was attempted. Approved synthetic relocation smoke passed.
