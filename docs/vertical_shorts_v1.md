# Vertical Shorts export V1

An optional FFmpeg-only 9:16 export of the same persisted highlight windows.
Center cropping is a deterministic baseline requiring no model, tracking or new
selection policy. The default remains the existing horizontal export.

## CLI

The existing positional video and required analysis arguments are retained:

    python export_shorts.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --format vertical --dry-run
    python export_shorts.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --format vertical
    python export_shorts.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --format vertical --cache-only

Use --format horizontal (or omit --format) for the original behavior. The unified
pipeline.py CLI remains unchanged and exports the default horizontal format.
The saved artifact still supplies five preselected Audio-only anchors, not fresh
multimodal ranking. Other existing --top-k/provenance restrictions remain intact.

## Encoding and timing

Vertical MP4 uses 1080x1920, H.264/libx264, yuv420p, CRF 18, preset fast and
AAC at 192k, with faststart. The source's first audio stream is retained and
re-encoded as before; no replacement audio, music or muting is introduced.
Candidate times and clamped [-10,+5] windows are unchanged.

Filter chain:

    scale=iw*sar:ih,setsar=1,scale=1080:1920:force_original_aspect_ratio=increase:force_divisible_by=2,crop=1080:1920:(iw-ow)/2:(ih-oh)/2,setsar=1

The first scale normalizes non-square source pixels; the next scale fills the
target while preserving aspect ratio. Center cropping removes excess picture,
without letterboxing. Final dimensions are even and sample aspect ratio is 1:1.
Vertical outputs are probed before publication/reuse for dimensions, pixel aspect
ratio and H.264/AAC, in addition to existing duration/integrity checks.

## Paths and cache compatibility

- Horizontal: output/<source-stem>/shorts/, unchanged.
- Vertical: output/<source-stem>/shorts_vertical/.
- Clip basenames and shorts_manifest.json follow existing naming conventions.
- Both default directories are already Git-ignored.

Horizontal encoding metadata stays exactly as before: no new default field, schema
version or signature change. Vertical encoding metadata adds format, width, height
and video_filter. Existing V1 cache comparison and V2 plan signatures already
include the full encoding object, so these fields distinguish formats without
changing source_identity.version=1 or source-content identity.

Normal vertical reuse also requires matching encoding metadata. Copying a
horizontal manifest into the vertical directory is rejected, not repaired.
--cache-only stays strictly read-only and rejects missing, corrupt or mismatched
artifacts without encoding, directory creation, manifest updates or migration.
Normal export retains its existing per-clip failure manifest behavior and atomic
temporary MP4 publication; failed clips do not publish partial MP4s.

V2 remains opt-in through --manifest-version 2 and retains the existing requirement
for a fresh isolated output root outside the default output tree. Use an external
local artifact directory outside Git, then reuse that same root with --cache-only.
V2 relocation accepts identical source content under the existing identity rules.
There is no legacy migration and V2 --force is still unsupported. Horizontal and
vertical artifacts can coexist; never hand-edit manifests to convert a format.

## Validation and limitations

Laptop synthetic validation: two-second 160x90 footage with sine audio exported
to 1080x1920 H.264, SAR 1:1, AAC. Both streams began at 0 and lasted 2.000 seconds;
duration error was 0. Cache-only reuse preserved synthetic hashes and nanosecond
mtimes. Only temporary synthetic media was encoded; production exports were not
regenerated. Mocked tests cover V1 compatibility, V2 relocation, cache misses,
format validation, unchanged timing, failed encodes and unrelated-file protection.

Center cropping can remove HUD, enemies, objectives and text near image edges.
Upscaling cannot recover detail. This is not subject-aware framing, and no captions,
publishing or narrative editing are added. Future intelligent reframing requires
separate evaluation before changing this deterministic baseline.

    python -m unittest test_vertical_shorts -q
    python verify.py
