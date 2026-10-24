# Windows dependency installer V1

`setup.ps1` prepares the export-only workflow. It resolves paths relative to its
own file and can be called from another working directory. It does not modify
export logic, saved analysis, media or research artifacts.

## Fresh Windows setup

Clone the repository and install a trusted 64-bit Python 3.14 and FFmpeg build
including FFprobe. Prefer your established Windows package manager (such as
WinGet), reviewing the exact package/publisher before approving installation.
Alternatively use Python's official Windows installer and a trusted FFmpeg
Windows build. Select libx264/AAC-capable FFmpeg, not just an FFprobe binary.
The locally verified reference is Python 3.14.0 and FFmpeg/FFprobe 9.0 Gyan full.
No universal minimum FFmpeg version or second-machine compatibility is claimed.

System installation is **guided, not automatic** in V1. setup prints missing
requirements and stops; it never invokes a package manager, elevates, downloads
binaries or edits PATH. The user controls system installation and all installer
permission prompts. Put the real Python executable and FFmpeg bin directory on
PATH through that explicit setup. Reopen PowerShell afterward and rerun checks.
Python launcher-only and Windows Store alias-only setups require this step;
setup deliberately avoids executing aliases/launchers that could install Python.

From Windows PowerShell 5.1 or PowerShell 7:

```powershell
.\setup.ps1 -CheckOnly
.\setup.ps1
.\setup.ps1 -SkipSmokeTest
# From elsewhere, substitute your actual checkout path:
& 'C:\Projects\gameplay-export\setup.ps1' -CheckOnly
```

If execution policy blocks the script, inspect it and use your organization's
approved signed-script or process-scoped execution procedure. setup does not
change execution policy or request administrative privileges.

## Plan, approval and reruns

The default mode checks system prerequisites, shows a plan, and requires literal
`YES` before creating `.venv`. Creation uses the verified Python family with
`venv --without-pip`: no package downloads or pip upgrade. New environments are
validated before diagnostics and the synthetic portability smoke test. When
reusing an existing environment, running the smoke test requires separate approval
because it creates temporary fixtures. Declining returns nonzero without repairs.

A compatible existing `.venv` is reused, never deleted or recreated. An incomplete,
relocated or incompatible environment fails with a manual-review message; there
is no global fallback. Successful stages can be reused on a later run. A failed
creation may leave an incomplete environment for the user to inspect. Setup does
not automatically repair it or remove unrelated packages.

`-CheckOnly` does not create `.venv`, install, download, run the smoke test or
write bytecode. With no `.venv`, it uses a supported system interpreter for
read-only diagnostics and reports missing project setup with exit code 1.
With a valid environment and system tools it returns 0. `-SkipSmokeTest` still
runs environment diagnostics but cannot establish functional codec compatibility.
All failures return nonzero; successful setup returns 0.

## Audited dependency profile

The export dependency closure is pipeline, both exporters, shared_analysis,
source_identity, transcription's lazy media helpers, media_probe, windows,
semantic_events and evaluation. Their export paths use only the standard library.
`requirements-export.txt` is intentionally comment-only: **zero third-party
packages**. Therefore there is no required-package install/upgrade or missing
required-package scenario for V1. If a requirement is added, setup fails closed
until the installer is reviewed; it does not interpret arbitrary pip directives.
A generic package installer would be unnecessary scope for this empty profile.

No global or local pip command is used. Optional ML, transcription, language,
CLIP/VLM and plotting dependencies stay in separate profiles. Diagnostics run
with `-B -S`; site packages are hidden, so optional packages can appear missing
even if installed globally. That is not an export failure. No models or CUDA are
initialized. Python 3.14 x64 is deliberately required; >=3.11 is only an inferred
API floor, not a tested installer support matrix.

## Verification and limits

Local test date: 2026-10-24. PowerShell 7.6.5 and Windows PowerShell
5.1.26100.9711, Windows 11 x64, Python 3.14.0 and
FFmpeg/FFprobe 9.0. Real CheckOnly detected these tools and returned 1 because
`.venv` was absent. No real installation or environment creation was performed.
Automated tests mock installation, approval and system-discovery scenarios;
Real CheckOnly passed its expected missing-venv checks under both shells from
outside the repository cwd, with hashes/mtime_ns unchanged. Actual installation
on either runtime and second-computer setup remain unverified.

On a second Windows computer, record commit ID and tool versions, then run
CheckOnly, approve setup, and require diagnostics and smoke PASS. Follow with:

```powershell
.\.venv\Scripts\python.exe verify.py
.\.venv\Scripts\python.exe -B -S portability_smoke.py
```

Smoke encoding uses disposable synthetic media only. Existing production cached
exports should be validated separately with the established read-only verifier.
See [second-machine guide](second_windows_export_v1.md) for transfer rules and
filesystem requirements. No RTX 4090, GPU or second-machine validation occurred.
Timeout/version/codec errors are failures to investigate, not permission to weaken
cache validation. Antivirus locks, cloud sync, unavailable hard links or concurrent
writers may prevent smoke success. Stop other writers and preserve production
artifacts; the setup script never repairs them.
