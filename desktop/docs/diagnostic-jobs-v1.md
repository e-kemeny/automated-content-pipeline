# Diagnostic jobs — Milestone 06

The Studio diagnostic is a real Python subprocess, not video processing. It runs
four interpreter metadata checks, four JSON round-trip checks, and four SHA-256
self-tests. Each check has one second of intentional pacing so cancellation is
reviewable. The reported 0–12 count reflects completed checks; no production
progress or video results are simulated.

## Run and review

From repository root:

```powershell
npm --prefix desktop run tauri -- dev
```

Use **Run diagnostic**, observe stages, then **Cancel diagnostic** or allow
completion. A terminal job enables another run. Navigation does not stop the
job; the component stays mounted and Rust owns the state. Browser preview leaves
native controls disabled. Video selection remains metadata-only and unrelated.

Interpreter selection and resource integrity follow
[python-worker-v1.md](python-worker-v1.md). No additional dependencies are needed.

## Authoritative lifecycle

Rust manages one diagnostic job at a time:
Idle -> Starting -> Running -> Completed/Failed; Starting or Running can enter
Cancelling -> Cancelled. Startup failure can enter Failed. A terminal outcome
cannot be overwritten. Completion requires the final validated worker message,
all twelve checks, successful process exit, and cleanup.

Each snapshot contains jobId, state, stage, startedAt/finishedAt (Unix milliseconds),
progress {completed,total}, optional structured error, and an application-wide
monotonically increasing revision. IDs combine the process session timestamp and
a generation counter. Only the latest job is retained, in memory.

Reservation and state transitions hold a short mutex. Process I/O, waiting,
termination, reader joining, and frontend emission occur outside that mutex.
Duplicate starts fail. Cancellation includes the expected jobId, so stale clients
cannot cancel a new job. If cancellation acquires the state lock before terminal
publication, Cancelled wins; after terminal publication, cancellation is a no-op.
Cancelling remains active until process cleanup completes, preventing early restart.

The argument-free start_diagnostic_job and get_job_state commands and the
job-ID-only cancel_diagnostic_job command are available to the local main window.
Rust emits full diagnostic-job snapshots for state/progress changes. The frontend
subscribes before fetching a snapshot, rejects stale revisions (including late
command responses), unsubscribes on cleanup, and reconciles on reload/window focus.
It cannot set authoritative state or emit native job events.

## Worker protocol

Health-check v1 behavior remains unchanged. Diagnostic requests use the same
bounded one-request/EOF input, with matching request_id and job_id:

```json
{"protocol_version":1,"request_id":"diagnostic-example-1","job_id":"diagnostic-example-1","command":"diagnostic_job"}
```

Each stdout line is an independently flushed JSON event, for example:

```json
{"protocol_version":1,"request_id":"diagnostic-example-1","job_id":"diagnostic-example-1","command":"diagnostic_job","sequence":2,"event":"progress","stage":"Interpreter","completed":1,"total":12,"error":null}
```

Events: started, progress, completed, failed. The successful stream has sequence
1–14: started, twelve progress events, completed. Failed events include
{code,message}; Rust errors additionally retain capped stderr. Input errors use
the existing structured rejection envelope and cannot produce job success.
Rust checks exact fields, identities, version, consecutive sequence, stage/count
consistency, final-message consistency, EOF and exit status.

## Containment and limits

The existing fixed worker resource, byte verification, interpreter resolution,
isolated Python flags, child guard, and Windows kill-on-close Job Object are
reused. There is no shell, user-provided script, media processing, or worker pool.

A dedicated blocking task owns each child. A bounded channel drains stdout with a
4 KiB per-line limit; stderr is capped at 64 KiB. The diagnostic has a separate
30-second execution timeout after process creation and request delivery. Windows process creation is synchronous on the blocking executor and can take several seconds under load; it is not covered by that execution deadline. Cancellation/timeout/protocol failure kills and reaps the
child, closes its Job Object (terminating descendants), and joins readers before
publishing a terminal snapshot. The channel is dropped before joining so a full
queue cannot deadlock cleanup.

On normal application exit, Rust rejects new work, requests cancellation, prevents
immediate exit, and waits off the UI thread for cleanup (bounded to 32 seconds).
Windows Job Object handle closure is the fallback if the application terminates
abruptly. The process guard is assigned before sending work. As in Milestone 05,
this trusts the installed interpreter and application files; it is not a sandbox
for arbitrary programs. Descendant containment is Windows-specific; other OS
deployment is not claimed verified.

## Tests

```powershell
python -B -m unittest discover -s desktop/worker -p "test_*.py" -v
npm --prefix desktop test
npm --prefix desktop run build
cargo check --locked --manifest-path desktop/src-tauri/Cargo.toml
cargo test --locked --manifest-path desktop/src-tauri/Cargo.toml
npm --prefix desktop run tauri -- build --debug --no-bundle
```

Python unit tests remove pacing through an injected sleeper; a real subprocess
test checks initial streaming. Rust tests include a full twelve-second real job,
running cancellation, startup cancellation without spawning, invalid/crashing
workers, timeout cleanup, descendant containment, state ordering, and restart.
Frontend tests mock transports and verify parsing, revision handling, subscription
cleanup/reconciliation, errors, and browser fallback.

There is no durable job history, reconnect across application restarts, persistent
pool, production cancellation contract, or video processing. Desktop deployment,
screen-reader behavior, and abrupt OS termination require separate review.

## Local verification

On the Windows development machine, 11 Python tests, 22 frontend tests, and 22
Rust tests passed (55 total, no failures or skipped tests). TypeScript, production
frontend build, locked Cargo check, and the native debug executable build passed.

The compiled native application was exercised with actual Python: live progress,
completion at 12/12, cancellation at 4/12, restart after cancellation, and Review /
Exports navigation during execution. Closing the window during another run at
3/12 checks removed both the native app and its observed worker process. The final
WebView2 progress bar was verified orange. These are local smoke tests, not a claim
of validation on another computer. Browser fallback, malformed messages, race
ordering, and subscription cleanup additionally have automated coverage; frontend
transport tests use mocks. Manual accessibility and desktop-machine acceptance
remain outstanding.
