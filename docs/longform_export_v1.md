# Long-form Selection & Assembly V1

A deterministic baseline joins chronological source intervals around persisted
preselected candidate timestamps. It is not a validated narrative editor and
does not claim coherent storytelling or retention optimization.

## CLI

From the repository root:

    python export_longform.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json --dry-run
    python export_longform.py videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Options: --seconds-before (15), --seconds-after (15), --merge-gap (5),
--output-root (output), --dry-run and --force.
Context/gap must be finite and nonnegative, and each expanded interval must
contain footage. Python standard library and FFmpeg/FFprobe are sufficient.
No CUDA or machine-specific paths are assumed.

Source existence, audio/video streams, persisted SHA-256 identity, duration and
Shared Analysis schema are validated through the existing Shorts planning
utility. Long-form does not call Shorts export, change Shorts code, rerank
candidates, or update the analysis document.

## Input and planning

The current artifact contains only five already-selected Audio-only windows:
40, 69, 84, 146 and 170 seconds. Provenance identifies
output/dynamic_window_v2.json, detector Audio-only, k=5, variant=fixed.
These are reused as preselected anchors, not a complete pool or multimodal
ranking. Missing/empty/ambiguous input is rejected without analysis fallback.
V1 supports preselected Audio-only or Audio + Scene fixed evidence; complete
candidate pools are rejected because no new long-form ranking policy is defined.

Expand every anchor using windows.build_candidate_windows:
start=max(0,anchor-seconds_before), end=min(duration,anchor+seconds_after).
Sort chronologically. Merge when next.start <= current.end + merge_gap, extending
end to max(current.end,next.end). Thus touching/overlapping windows are never
duplicated; a nearby gap is retained as context inside the merged interval.
Preserve original anchors and source timestamps; never assign semantic events.

Default real expansion:

| Anchor | Source window |
|---:|---:|
| 40 | 25-55 |
| 69 | 54-84 |
| 84 | 69-99 |
| 146 | 131-161 |
| 170 | 155-185 |

Merged plan: [25,99] (74 seconds), [131,185] (54 seconds).
Estimated assembled duration: 128 seconds, two source intervals.
This differs from Shorts: Shorts exports five independent [-10,+5] windows;
long-form expands and merges context, then concatenates a single horizontal MP4.
Neither mode uses language scores, CLIP/semantic evidence or retention to select.

## Assembly and outputs

    output/<source-stem>/longform/
        longform_v1.mp4
        longform_manifest.json

Accurate FFmpeg seeking re-encodes each source interval as H.264/yuv420p
(CRF18, preset fast) with a common source-derived CFR, 48 kHz stereo PCM audio
and original source dimensions. Temporary MKV segments are concatenated in
chronology; video is copied from the normalized segments and audio is encoded
once to AAC 192 kbps in the final fast-start MP4. PCM avoids adding AAC encoder
padding independently to each intermediate segment.

Each segment and the assembled result are probed for audio/video streams and
duration. Verification reuses Shorts' frame/packet precision check: duration
error may not exceed the larger of one frame or 50 ms. This verification does
not modify detector or evaluation tolerances. Source/analysis hashes are checked
again before publication. Temporary segments are cleaned up on success/failure.

Manifest separates planning from assembly. It includes actual source identity
and duration, analysis schema/hash, selection provenance/evidence, anchors,
configured context/gap, expanded and merged intervals, segment count, estimated
duration, actual assembled duration, output path/hash, encoding settings,
verification, export statuses and errors. Failed segments cause subsequent
segments to be marked skipped; no incomplete sequence is declared successful.
A concat failure keeps actual duration null and assembly status failed.

## Reuse and safe replacement

Dry run checks inputs and prints the plan without encoding or writing outputs.
Cache identity binds source hash/duration, candidate evidence/provenance, context,
merge gap, merged plan and encoding settings. Unrelated analysis signals such
as language scores do not invalidate the assembly plan. A valid final output is
hash-checked and probed; repeat invocation reuses it without any encoding.
Segments are marked reused_from_final, since intermediates are temporary.

A changed plan/config requires --force when a generated final file exists.
Force only replaces an unchanged, exporter-owned output, after the new result
passes verification. Unrelated/edited outputs, symlinks, unrelated manifests
and concurrently changed files are rejected even with force. No-force
publication is exclusive and cannot overwrite an output created concurrently.
A failed forced refresh retains the old MP4 and records its ownership separately
from the failed new plan; it is never reported as a successful new assembly.

JSON is indented and deterministic. Manifest publication uses a unique temporary
sibling. No unrelated outputs are deleted, and the source/Shared Analysis/Shorts
files remain unchanged. Full cross-process locking is not provided: interruption
can leave a valid MP4 without its manifest, which is conservatively treated as
unowned next time.

## Limitations

Context sizes and merge gap are baseline settings, not tuned against this
video's annotations or viewer behavior. Cuts may interrupt dialogue or gameplay.
There are no transitions, story structure, subtitles, music, reframing, publishing
or GUI. Stream metadata and decoding checks can detect technical problems, but
human viewing is still needed to judge cut continuity and perceptual A/V sync.
No detectors, transcription or ML inference run during this workflow.

## Real BedWars validation

The default dry run produced the two intervals above without writing outputs.
One real export completed successfully: expected/container duration 128.000 s.
FFprobe identified H.264 video and AAC audio, both with stream start time 0.
Video stream duration was 127.999 s and audio 128.000 s: a 1 ms discrepancy
consistent with intermediate MKV timestamp quantization. Both source segment
container durations matched their requested 74/54 seconds exactly.

All 7,680 video packets and 6,001 audio packets had strictly increasing DTS.
Initial negative DTS from H.264 reordering/AAC priming is normal; presentation
starts at zero. The full output decoded without FFmpeg errors. No technical
A/V issue was detected; perceptual lip-sync was not independently assessed.

Real cache reuse ran with encoding forbidden, preserved MP4 hash/mtime and
left Shared Analysis bytes unchanged. The final suite passed 253 unit tests
plus four standalone motion checks; baseline was 228 plus four. Output files
remain ignored under output/. No existing implementation or experiment changed.
