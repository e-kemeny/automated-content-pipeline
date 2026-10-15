# Shorts Selection & Export V1

Export standalone review clips from a source video and persisted Shared Analysis
V1 without running detectors or models. No reframing, captions, music or publishing.

## CLI

From the repository root:

    python export_shorts.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --top-k 5 --dry-run
    python export_shorts.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --top-k 5

--output-root defaults to output and is configurable. --force permits replacing
only unchanged, previously generated clips owned by this exporter. No CUDA or
inference dependencies are needed: Python standard library and FFmpeg/FFprobe.

The source must exist and contain video/audio streams, match the persisted
SHA-256 identity and match its duration (numeric tolerance 1 microsecond).
Unsupported analysis versions, missing candidate evidence, or ambiguous
candidate provenance are rejected. The analysis document is never written.

## Selection policy

The real shared_analysis_v1.json contains five already-selected fixed windows,
with provenance detector Audio-only, k=5, variant=fixed. It is NOT a complete
candidate pool and NOT an Audio + Scene selection. V1 explicitly reuses these
five timestamps, in chronological order, and requires top-k exactly 5.
It does not rerank them by available highlight_score metadata.

Other persisted selections must explicitly identify Audio-only or Audio + Scene,
variant=fixed, and k equal to their row count. They must satisfy the frozen
15-second separation; a requested subset or larger top-k fails instead of
guessing the original suppressed ranking.

A future persisted complete pool can explicitly declare
candidate_windows.provenance.representation=candidate_pool,
detector=Audio + Scene and variant=fixed. Every row must retain its original
highlight_score and unique nonnegative integer ranking_order to preserve the
original stable tie order despite chronological storage. The exporter then
calls the existing evaluation.select_highlights helper: descending frozen
highlight_score, greedy timestamp separation >=15 seconds, chronological output.
A pool that cannot supply the requested number after suppression fails clearly.
No scores, weights, candidate evidence or pool membership are reconstructed.

All boundaries use windows.build_candidate_windows defaults:
start=max(0,second-10), end=min(source_duration,second+5).
Persisted timestamps remain unchanged. Dynamic cuts and experimental semantic,
language, CLIP and motion scores do not affect selection.

## Layout and manifest

    output/<source-stem>/shorts/
        clip_01_t00040.000.mp4
        ...
        shorts_manifest.json

Names use chronological index and candidate time to milliseconds. Exact original
timestamps and boundaries remain in JSON. Each manifest contains actual source
identity/duration, shared schema version and analysis-file hash, selection mode,
detector, original ranking-score key, top-k, policy/provenance, candidate evidence,
filename, status/error, verification and output-file hash.

Audio-only ranking_score is the original raw audio score; Audio + Scene uses
highlight_score. Other copied candidate fields are evidence, not active ranking
signals. No semantic/language scores are synthesized or used.

Dry run validates input and previews planned paths but creates no directories,
clips or manifest. It performs source FFprobe/hash checks only.

## Encoding and safety

Accurate FFmpeg input seeking followed by H.264 (libx264, CRF18, preset fast) and
AAC (192 kbps) re-encoding avoids stream-copy keyframe boundary shifts. Both
streams are mapped from the same source and original aspect ratio is retained.
Playable stream metadata and duration are checked with FFprobe after encoding.
duration_error_seconds records container duration minus requested duration;
frame/AAC packet quantization can introduce small discrepancies. Exports whose
duration error exceeds the larger of one video frame or 50 ms fail verification;
this is an encoding check, not a change to detector/evaluation tolerances.

Unique temporary outputs are verified before publication. Publication without
force is exclusive; a target that appears concurrently is not overwritten.
Owned existing clips are hash-checked and reused without encoding. Force
replaces owned unchanged clips only; unrelated files, edited clips, symlinks,
other-source manifests and concurrently changed manifests are rejected.
A failed forced refresh retains the previous owned MP4. Individual encoding
failures are recorded; other clips continue and CLI returns a nonzero exit code.
The manifest is deterministic JSON, written through a unique sibling temporary
file. No unrelated files are deleted; repeated manifests may change clip status
from exported to reused while clip bytes stay unchanged.

## Limitations

This is review/export infrastructure, not validated semantic Shorts selection.
The supplied artifact reuses Audio-only evidence, so the available data cannot
support a new Audio + Scene top-k experiment or Top 10 export. Provide explicitly
persisted compatible evidence to support those operations; no hidden analysis
fallback exists. Missing source identity requires regenerating metadata outside
this exporter, not silently accepting a different source.

No complete concurrency lock across all exports is provided. Exclusive file
publication and manifest checks prevent unrelated overwrite; an interrupted run
may leave valid clips without a completed manifest, which are conservatively
treated as unowned on the next run. Human review is still required.

## Strict cache-only verification

Add --cache-only to validate and reuse existing outputs without writing any
artifact or creating directories. It conflicts with --force and --dry-run
(CLI exit code 2). Missing/invalid/stale caches fail with a nonzero exit code;
there is no encoding, repair, or inference fallback.

The current source identity, shared-analysis hash/version, selection/planning
configuration, successful manifest records, MP4 hashes, audio/video streams and
durations must validate. Cache-only is intentionally stricter than normal reuse:
even unrelated changes to the analysis JSON invalidate its saved hash.
FFprobe and file hashing are read-only; source analysis is not rerun.
Returned reuse statuses exist only in memory: manifests remain byte-for-byte
unchanged. Normal export behavior is unchanged.

    python pipeline.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --mode both --cache-only

Both mode reports each exporter separately and returns nonzero on partial
failure. Each exporter CLI also accepts --cache-only. No cross-process lock is
provided: a disappearing artifact causes failure, never encoding. Avoid concurrent
writers during verification; these checks cannot prevent another process from
changing a file after the final read. Stream metadata checks are not a full
decode or perceptual playback assessment.
