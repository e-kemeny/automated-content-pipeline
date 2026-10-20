# Artifact relocation audit V1

Audit date: 2026-10-20. Read-only inspection of current production JSON; relocation
exercised on small temporary fixtures. No identity policies or artifacts migrated.

## Actual saved fields and their roles

| Location | Observed representation | Validation / portability role |
|---|---|---|
| Analysis source_video.path | Relative videos/my_recording.mp4 | Schema requires a nonempty string, not an existing path. Export probes the CLI source instead; this locator is not directly compared to its resolved path |
| Analysis source_video.sha256, duration_seconds | SHA-256; 231.433288 seconds | Export requires matching source bytes and duration (absolute tolerance 1e-6). These are real content/timing safeguards |
| Analysis schema_version | 1 | Validated; unsupported schemas fail |
| Analysis candidate_windows | Five preselected Audio-only anchors, fixed windows, scores; artifact output/dynamic_window_v2.json | Selection/evidence and provenance are copied into manifests and compared; the referenced artifact is not opened by export |
| Analysis semantic_events.provenance.artifact | output/clip_semantic_events.json | Historical locator; export does not open it |
| Analysis transcript/language/visual provenance | Model/revision/options, signatures, processing times and observations | Preserved evidence; not active export ranking. All JSON bytes still affect the analysis-file hash |
| Both manifests source.path | Absolute Windows checkout path ending in videos/my_recording.mp4 | Cache-only compares the ENTIRE source dictionary, so this path is identity-bound even for identical bytes |
| Both manifests source | sha256, duration_seconds, width=1920, height=1080, fps=60 | Reprobed source must equal saved dictionary in cache-only mode; path plus technical metadata can couple reuse to location/probe representation |
| Both manifests shared_analysis | Relative output\\shared_analysis_v1.json, schema_version, raw-file SHA-256 | Cache-only compares hash/version, NOT this path. Identical JSON can move unchanged |
| Shorts clips[].output_filename | clip_01_t00040.000.mp4 through five chronological clips | Resolved under current output root/source stem/shorts. Exact expected filename set and clip records are validated |
| Shorts clips[] | Candidate time, bounds/duration, original ranking key/score, evidence, status/error, output_sha256, verification | Evidence/bounds and successful status checked; current MP4 bytes/streams/duration validated |
| Long-form assembly.output_path | Absolute checkout path ending in output/my_recording/longform/longform_v1.mp4 | Saved path is informational for cache validation; current output path is reconstructed. It is not part of the plan signature |
| Long-form plan_signature | SHA-256 of serialized exporter/source hash+duration/planning/encoding | Does not directly include source.path, shared_analysis.path or assembly.output_path. Provenance inside planning is included |
| Long-form planning/segments/assembly | Anchors, expanded/merged intervals, configuration, counts, status/error, output hash, stream verification/duration | Plan equality/signature, successful records and output integrity checked |

The real source SHA-256 is
6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09.
No persisted filesystem size or modification-time identity field was found in
these three JSON documents. Video/event timestamps and processing durations are
not filesystem timestamps. verify.py records sizes transiently while hashing and
compares SHA-256 plus st_mtime_ns before/after a run; it does not require mtimes
from the original computer. Copy-time mtime changes alone do not invalidate caches.

Absolute manifest source/output paths are machine-specific. Relative provenance
paths assume the historical project layout, but are not automatically resolved
or repaired. A broad text replacement is unsafe: even an informational edit to
analysis changes its raw-file hash, and selection provenance affects plan equality.

## Tested scenarios (both exporters, strict cache-only)

| Scenario | Actual result / exact reason |
|---|---|
| Original fixture paths | Pass; reused without writes |
| Entire repository fixture copied to another absolute directory | Fail: Cache-only stale manifest: source |
| Source moved, same basename and identical bytes | Planning passes; cached reuse fails: Cache-only stale manifest: source |
| Source bytes changed at same path | Fail: Source identity mismatch |
| Source missing | FileNotFoundError: Media file not found: followed by resolved path |
| Analysis moved without editing its bytes | Pass with unchanged source and output root |
| Outputs/manifests copied to new output root, original source retained | Pass using exporter output_root; old Long-form output_path does not block reuse |
| Only analysis source locator edited | Fail: Cache-only stale shared analysis (raw JSON hash changed) |
| Manifest source hash changed | Shorts: Cache-only stale manifest: source; Long-form: Existing manifest is unrelated or invalid; refusing replacement |
| Manifest analysis hash changed | Fail: Cache-only stale shared analysis |

All scenarios snapshot fixture bytes/hashes and nanosecond mtimes after deliberate
setup/mutations, then assert no changes during cache-only calls. Directory creation,
external subprocesses and temporary output creation are forbidden during those
calls. Probe responses are mocked; actual require_media, source/output hashing,
shared schema loading, planners and cache validators run. Fixture artifacts are
synthetic bytes, not actual playable MP4s; real production probing is covered by
the separate cached verification run. No large media is copied for relocation.

## Can current artifacts move unchanged?

Not as a complete relocated checkout with a moved source: current strict source
path equality rejects it, despite the unchanged video hash. The shared-analysis
JSON itself remains loadable. If the source remains at the original resolved path,
analysis and exports can move unchanged as tested. Recreating the same absolute
source path on another computer may avoid this particular mismatch, but is not
second-machine verification; all metadata, hashes and tooling still must match.
Renaming the video also changes video.stem-based output discovery and may produce
missing-manifest failures before reaching content validation.

pipeline.py uses the current working directory's default output root and forwards
CLI input paths. verify.py anchors output discovery/subprocess CWD to its own
repository, resolves CLI inputs and currently expects nine artifacts/five Shorts.
The individual exporters support an explicit output_root; neither CLI wrapper nor
verification silently searches previous locations. Symlink and input/output
collision restrictions remain intentional protections.

Normal reuse is intentionally different: it can rewrite manifests and, for absent
outputs, encode. Its source ownership checks are less path-coupled than cache-only.
Do not use a normal export to repair relocation during an audit.

## Safety versus path coupling

Source-byte identity, source duration, expected plan/evidence, successful status,
output hashes, playable stream metadata and encoding configuration are legitimate
safety checks. Rejecting identical content solely because source.path changed is
additional location coupling. Exact source metadata equality can also reject
representational differences across FFprobe builds; that is not tested away here.
Analysis raw-byte hashing intentionally catches ALL edits, including formatting
and informational locators. Weakening it to semantic equality would be a separate
policy change, not a relocation shortcut.

## Recommended next milestone

Define and test a versioned portable source-identity contract before writing a
migration utility: distinguish content identity (hash and required technical
metadata) from locators and historical provenance. Specify compatibility with
old manifests, no silent acceptance of changed bytes, and preservation of original
artifacts. Keep export policy and model contracts unchanged.

A later explicit migration should be dry-run-first, operate on copies, verify
source/output hashes and all plans, retain original path provenance, record old/new
artifact hashes, and publish a new manifest version atomically. It must never
blindly rewrite paths, repair MP4s or invoke inference. Decide how raw analysis
hashes and relocation-only edits interact before implementation. Validate on a
second Windows computer only after fixture coverage and local cache-only parity.
No migration or production-policy change is implemented by this audit.
