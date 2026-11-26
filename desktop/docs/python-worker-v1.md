# Python worker adapter — Milestone 05

This optional one-shot health check connects React -> Rust -> Python. It does not
import or connect the production pipeline, inspect videos, or enable processing.
The header remains compact; hover or keyboard-focus it for runtime details.

## Run

From repository root, with an installed Python 3 interpreter:

```powershell
npm --prefix desktop run tauri -- dev
```

Rust resolves the interpreter in this order:
1. CONTENT_PIPELINE_PYTHON: an existing absolute executable path supplied by the
   launching environment, never the frontend.
2. VIRTUAL_ENV/Scripts/python.exe on Windows (bin/python elsewhere).
3. python.exe on Windows or python3 elsewhere, using the host executable search.

An invalid explicit override/environment fails rather than silently using another
interpreter. Use a trusted Python installation and trusted PATH; Windows Store
aliases or a GUI launch with a different inherited environment can fail. For a
specific environment, set CONTENT_PIPELINE_PYTHON in the launching PowerShell
session, then run the command above. No global settings or PATH changes are made.
The worker uses only Python's standard library; no environment packages are needed.

## Protocol v1

One UTF-8 JSON request on stdin, followed by EOF; one JSON response on stdout.
Stderr is reserved for diagnostics. Maximum request: 4 KiB. Captured stdout/stderr:
64 KiB each, plus one byte to detect overflow. Example request:

```json
{"request_id":"health-1","protocol_version":1,"command":"health_check"}
```

Example successful response (runtime values vary by machine):

```json
{"request_id":"health-1","protocol_version":1,"command":"health_check","status":"ok","data":{"pythonVersion":"3.14.0","operatingSystem":"Windows","cpuArchitecture":"AMD64","workerProtocolVersion":1},"error":null}
```

Example failure:

```json
{"request_id":"health-1","protocol_version":1,"command":"health_check","status":"error","data":null,"error":{"code":"unsupported_version","message":"Unsupported protocol version."}}
```

Malformed requests return invalid_request (request_id is null when unavailable).
Unsupported commands return unsupported_command. The response command identifies
this adapter's sole command, health_check. Protocol rejections are successful
process exits with error envelopes; infrastructure failures are separate Rust
errors with code, message, and captured stderr.

## Lifecycle and security

The argument-free native check_python_worker command is permitted only for the
local main window. Rust chooses the fixed worker/worker.py resource, verifies its
bytes against the application build, and launches Python with direct -I -B
arguments (isolated mode, no bytecode writes). No shell or frontend-controlled
command, executable, arguments, or script path is accepted. Resource mapping uses
Tauri's resource directory in development and standalone builds.

Blocking subprocess work runs on Tauri's blocking executor. Stdin closes after the
small request. Separate capped readers drain stdout and stderr. A five-second
process-wait limit triggers kill and wait; a child ownership guard also kills/reaps
on error paths. On Windows a non-inheritable kill-on-close Job Object guards worker
lifetime on application exit. Failure to attach the guard fails closed. Assignment
occurs immediately after spawning, before sending the request; this is not a
sandbox for an untrusted interpreter. Only the trusted one-shot worker is supported.

Rust validates request ID, command, protocol version, exact envelope, status/data/
error consistency and nonempty runtime strings before returning typed health data.
There is no persistent worker pool. A native mutex rejects simultaneous checks;
React caches the check for the page session, including development StrictMode.
Reopen/reload to retry after changing the interpreter environment.

Availability means health check success only. Browser mode never starts a worker.
Native IPC failure remains Runtime unavailable; worker failure leaves native
readiness visible in the tooltip. No media/job capability is implied.

## Checks

```powershell
python -B -m unittest discover -s desktop/worker -p test_worker.py -v
npm --prefix desktop test
npm --prefix desktop run build
cargo check --locked --manifest-path desktop/src-tauri/Cargo.toml
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
npm --prefix desktop run tauri -- build --debug --no-bundle
```

Python tests include real one-shot subprocess checks. Rust tests include actual
Python execution, invalid-output/nonzero-exit fixtures, timeout/reaping, and Windows
Job Object termination; they require Python but no media or model dependencies.
Frontend tests inject responses/failures and do not require Tauri or Python.

No Python or npm dependencies were added. serde_json and windows-sys (Windows
process lifetime support) are direct Rust dependencies using already-resolved
versions. Desktop deployment and non-Windows lifecycle behavior need separate
verification; no Python runtime or installer is bundled.

Local verification: Python 3.14.0 on Windows/AMD64 returned through the real native
application and displayed Python worker available. Studio, Review and Exports
navigation worked. Failure UI presentation and browser fallback were exercised
with injected frontend transports; the real desktop test exercised success.
No desktop RTX 4090 or other operating-system validation is claimed.
