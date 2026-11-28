# Real video processing V1 (Milestone 07)

## Run

From `desktop/`, run `npm run tauri -- dev`. Select a video, choose Shorts,
Long-form or Both, choose an existing output folder, then Start. Cancel stops the
active process tree. Python, FFmpeg and FFprobe must already be installed and
available to the application environment; worker health alone does not verify them.
Browser preview keeps metadata-only selection and never starts processing.

## Integration and ownership

`worker/processing.py` reuses `dev_test.paths_for`, `obtain_analysis`,
`review_text` and `publish_review`, plus the existing Shorts/Long-form exporter
functions. Dense collection, source identity, shared-analysis publication,
selection, encoding and strict cache validation remain production implementations.
No production module changed. The frozen Audio-only baseline requires five valid,
15-second-separated candidates; it never pads missing candidates. Silence can
produce baseline candidates and is not evidence that those clips are interesting.
Input must have both video and audio streams.

Each run exclusively creates a new `content-pipeline-<job-id>` folder beneath the
native-selected output folder. `desktop_job.json` records ownership, not successful
completion. Existing unrelated files are never replaced. Scratch data, partial
files and failed runs remain inside that workspace for inspection; no automatic
repair, deletion, history or resume is implemented. Existing cache validation is
reused within the job, including a read-only exporter check before reporting
outputs. Separate runs do not discover or reuse each other's caches.

The native executable locates the engine through its compile-time repository root.
Keep the build checkout available; rebuild after relocating it. This is development
integration, not a portable installer or bundled Python/FFmpeg distribution.

## Protocol and progress

Rust owns the selected paths and source stat identity. React sends only an export
mode to `start_processing_job`; it cannot choose an executable or worker path.
Example worker request (illustrative local paths):

```json
{"protocol_version":1,"request_id":"request-1","job_id":"job-1","command":"process_video","config":{"video":"C:/media/source.mp4","workspace":"C:/output/content-pipeline-job-1","mode":"both","size_bytes":12345,"modified_ms":1700000000000}}
```

Actual stages are Validating source, Collecting observations and generating shared
analysis, Exporting Shorts and/or Exporting long-form, and Finalizing outputs.
Collection/selection are one combined stage because the reused function exposes
no finer progress callback. No percentages or ETA are invented.

```json
{"protocol_version":1,"request_id":"request-1","job_id":"job-1","command":"process_video","sequence":3,"event":"progress","stage":"Exporting Shorts","completed":0,"total":0,"error":null,"artifacts":[]}
```

Zero counters mean unknown work and render indeterminate progress. Ordered events,
request/job identity, stages and artifact schemas are validated. Final artifacts
include absolute path, kind, byte size, SHA-256 and optional video duration.
Both returns five Shorts, one Long-form, one review CSV and one shared-analysis JSON.
The final artifact list is exposed only after successful worker exit and cleanup.
An error or cancellation exposes no completed artifact list, even if partial files
exist. Pipeline prints go to stderr; stdout is exclusively NDJSON.

## Lifecycle and permissions

The existing one-job supervisor, duplicate rejection and Windows Job Object are
reused. Python and FFmpeg descendants are terminated/reaped on cancellation,
timeout or application shutdown. Processing has a four-hour execution bound;
the diagnostic job retains its 30-second bound. Reader threads drain diagnostics
while retaining bounded text. Blocking probes/pickers and processing run outside
the UI thread. Source size/mtime is checked again before execution, and production
hash/provenance checks remain authoritative. Symlinks/junctions and Windows reparse
points are rejected; download cloud-only files locally before selection.

The only new dependency is Rust `tauri-plugin-dialog` (locked 2.8.4), with locked
transitive `rfd` 0.17.2, `tauri-plugin` 2.7.4 and `tauri-plugin-fs` 2.7.1.
No JavaScript/Python dependency was added. Capabilities grant only the four narrow
application commands; no general frontend filesystem, shell or dialog access is
granted. Arguments are passed directly, never through shell interpolation.

## Verification

Baseline desktop: Python 11, frontend 22, Rust 22 (55 total).
Final desktop: Python 22, frontend 29, Rust 29 (80 total).
Production regression: 901 discovered, 900 passed, one deferred/skipped; four
motion checks passed. Strict cached production export verification passed.

Native compiled-app tests used an isolated ignored 80-second 320x180 synthetic
video with a Unicode/spaced filename. Both generated five playable Shorts and one
playable Long-form plus review/analysis files. Independent FFprobe found audio
and video streams in all six: Shorts 10.005333s, 15s, 15s, 15s, 15s; Long-form 80s.
The first clip differed by 5.333ms, within existing exporter tolerance.
Three synthetic runs completed (18 videos total); cancellation clicks on the two
fast repeats arrived after completion and correctly did not relabel success.
A separate run reading the existing gameplay source was cancelled while collecting
observations: zero MP4s, no completed artifact list, worker and FFmpeg gone after
cancellation. Native source/output pickers, real stage updates, Review/Exports
navigation and return-to-Studio persistence were exercised. Protected production
artifacts are independently checked by SHA-256 and nanosecond modification time.

Automated tests include real worker subprocess protocol/cleanup checks and mocked
pipeline/bridge cases. No models, inference or production export encoding ran.
Review/Exports remain their existing layouts; interactive output integration is
Milestone 08. Other-machine deployment, broader codec coverage and screen-reader
acceptance remain manual checks. Application-close containment retains the tested
supervisor behavior; this smoke test specifically exercised explicit cancellation.

## Intended source changes

Only `desktop/`: README; this document; worker/worker.py, processing.py,
test_processing.py; src/App.tsx, runtime.ts, processing.ts, styles.css,
components/Workspaces.tsx, ProcessingStudio.tsx; tests/worker.test.mjs,
processing.test.mjs; src-tauri/Cargo.toml, Cargo.lock, build.rs, tauri.conf.json,
capabilities/runtime.json; src-tauri/src/main.rs, worker.rs, jobs.rs, jobs_tests.rs,
media.rs, processing.rs; four generated command permission files for
get_media_selection, select_source_video, select_output_workspace and
start_processing_job. Generated media/build files and the unusual unrelated
untracked filename must not be staged.
