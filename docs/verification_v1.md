# Verification runner V1

From the repository root:

    python verify.py
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Both modes run the complete unittest discovery suite and the four standalone
motion checks, in separate subprocesses using sys.executable. Neither group is
skipped if the other fails. Optional integration is independently reported.
Any failed group/check returns exit code 1; invalid CLI arguments return 2.

The runner uses its repository directory as the subprocess working directory.
Explicit video/analysis paths resolve relative to the caller's working directory.
Default exporter output locations remain output/<source-stem>/shorts/ and
output/<source-stem>/longform/ under the repository.

## Cached integration prerequisites

Requires FFprobe on PATH, matching existing video/Shared Analysis V1, five Shorts,
one Long-form MP4, and both successful compatible manifests. Local runtime assets
are not included in a fresh clone. Existing read-only exporter planners identify
the expected files and validate source/schema/candidates; no selection or path
logic is duplicated. Missing artifacts fail before pipeline invocation.

The runner snapshots SHA-256 and st_mtime_ns for all nine artifacts (six MP4s,
two manifests, analysis), invokes pipeline.py --mode both --cache-only, then
checks all snapshots again, even on a pipeline failure. The pipeline exit code
reports whether both exporters succeeded. Cache eligibility, configuration,
hashes, stream/duration checks and no-write enforcement belong to the exporters.
The runner never invokes normal export, force, inference, encoding or repair.

## Limits

No directories or output artifacts are created by the integration check.
Unit tests intentionally use temporary fixtures; ordinary Python imports may
create bytecode caches. Unit tests mock model/encoding calls and do not download
models. Integration uses read-only FFprobe, not a full decode or visual review.

No concurrent-writer lock is provided. Avoid other writers during verification;
hash/mtime comparison detects changes at the checks, not a change later or an
external change reverted between checks. Timestamps may have filesystem-specific
precision despite using the nanosecond API. Failure never repairs assets:
investigate separately. This V1 targets the default five-Shorts export contract,
not arbitrary output roots or alternative long-form configurations.
