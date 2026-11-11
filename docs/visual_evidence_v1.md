# Game-Agnostic Visual Evidence Extraction V1

A standalone CPU sampling layer producing real PNG frames and optional crops. It performs no OCR, automatic game identification, semantic classification, model loading or highlight scoring. Production pipelines, human annotations and existing caches remain separate.

## Commands

From the repository root:

    python visual_evidence.py --video videos/my_recording.mp4 --output-root output/visual_evidence_v1

Default sampling is at least 2 seconds between selected frames, beginning at zero, capped at 120 frames, resized to 640x360. Explicitly opt into video processing by invoking this command; implementation validation used only disposable synthetic sources.

    python visual_evidence.py --video videos/my_recording.mp4 --output-root output/visual_evidence_bedwars_v1 --game bedwars --crops --interval 2 --start 20 --end 40 --max-frames 10 --width 640 --height 360

    python visual_evidence.py --video videos/my_recording.mp4 --output-root output/visual_evidence_custom_v1 --profile profiles/my_visual_profile.json --crops

--game and --profile are mutually exclusive. Unknown --game identifiers select generic extraction and record unknown_game_fallback=true; no game is inferred. An explicitly supplied malformed profile fails instead of silently falling back.

--expected-identity optionally accepts a JSON object in source_identity.py's version-1 content-identity format and requires an exact match. This extractor's identity includes duration, native width and height, without an optional FPS field. Omit the flag when there is no prior identity claim. There is no overwrite, repair or inference fallback option.

## Existing conventions reused

vision_inference.inspect_video provides first non-cover-art video-stream selection, positive duration/dimension checks and FFmpeg/FFprobe availability checks. It calls the existing media_probe transport. Importing that module does not load PyTorch or torchvision. source_identity.file_identity and validate_identity provide streaming SHA-256, byte count and the established identity contract.

The existing ResNet experiment's extract_frame helper records requested seek times, explicitly not measured PTS. It is intentionally not reused for timestamp assertions. The new extractor runs a single sequential FFmpeg decode with selection and showinfo; region crops decode the resulting PNG, never the original video again.

Only standard-library Python and installed FFmpeg/FFprobe are required. Export-only dependencies are sufficient; Pillow, NumPy, OCR, CUDA and ML environments are unnecessary and unchanged.

## Timestamp contract and sampling

FFmpeg receives the chosen stream with -copyts. The first filter, setpts=PTS-STARTPTS, explicitly makes the **first decoded video frame zero**. Selection uses that normalized clock:

- Include frames at or after start, strictly before end.
- Select the first eligible frame, then the first available frame at least interval seconds after the previously selected frame.
- Stop after max_frames (1-1000); default 120.
- No FPS filter, frame interpolation, output frame-rate forcing or input seeking.
- passthrough output timing and a trim filter before showinfo limit logging to the emitted frame set.

The manifest retains integer normalized_pts, its rational time_base, and timestamp_seconds calculated from those values. showinfo's rounded pts_time display is not used for arithmetic. PNG count/order must match logged timestamps exactly; non-increasing PTS, missing time bases for emitted images, out-of-range frames or inconsistent dimensions fail the bundle.

These are measured filter presentation timestamps, not requested seek times or an exact sampling grid. A start of 0.3 seconds at 4 FPS can yield the first sample at 0.5 seconds. Gaps/variable frame rates can move later samples away from a nominal grid.

The clock is **not** automatically equivalent to container start, audio time or existing transcript timestamps. Original container PTS offsets are not reconstructed. Do not merge this artifact into the existing multimodal timeline without an explicit clock-alignment adapter. No timeline schema extension is made here.

Video duration is FFprobe's container duration retained in source identity. It bounds the request but does not prove selected video-frame coverage, particularly with a nonzero source origin. Empty ranges (start=end) produce a valid no_frames bundle without decoding. A nonempty range with no eligible decoded frames also reports no_frames. Hitting the cap reports max_frame_limit_reached, not proof of whether further frames existed. Sparse samples cannot establish semantic or continuous visual coverage.

## Images and profiles

Frames are RGB24 PNGs resized to exact requested width/height (each integer 1-4096). Different aspect ratios stretch the image; choose matching dimensions if that matters. FFmpeg's normal orientation handling applies. Profiles refer to the resulting image coordinate system, not assumed game-specific HUD semantics.

Included configuration files:

- profiles/visual_generic_v1.json: game_id generic, full-frame region.
- profiles/visual_bedwars_v1.json: illustrative full frame, top-center, bottom-left and bottom-center regions. These are not validated HUD/text locations.

A profile has schema_version=1, profile_version=1, game_id, regions and optional-in-meaning ui_hints (an object, empty when unused). The strict JSON contract requires all five fields. Each region has name, x, y, width and height. Coordinates are finite normalized numbers, widths/heights positive, and rectangles must stay inside [0,1]. There may be 1-16 uniquely named regions. Names use lowercase letters, digits and underscores, beginning with a letter, at most 48 characters; they cannot introduce paths.

A custom game needs only another profile JSON:

    {
      "schema_version": 1,
      "profile_version": 1,
      "game_id": "my_game",
      "regions": [
        {"name": "full_frame", "x": 0, "y": 0, "width": 1, "height": 1}
      ],
      "ui_hints": {}
    }

Without --crops, configured regions remain metadata. With --crops, every configured region is extracted from each resized frame using FFmpeg. Pixel origins are rounded down and far edges up, clamped to image bounds. Both original normalized geometry and actual pixel rectangles are recorded. Each crop includes its parent frame ID, region name, relative image path, dimensions and SHA-256. No OCR text or event labels are fabricated.

## Manifest and safety

visual_evidence_manifest.json contains schema_version=1, artifact_type=visual-evidence, source_identity, informational source_location, container duration, sampling configuration, full profile, requested game/fallback status, frame rows, crop rows, extraction provenance, coverage and limitations.

Frame IDs hash source identity, measured PTS/time base and resized dimensions. Filenames combine sequence index and an ID prefix; crop names add the validated region name. Image/log paths are relative to the bundle. Images are not embedded in JSON. Full frame/crop digests and dimensions are recorded; dimensions are checked from PNG headers. extraction.log retains FFmpeg showinfo evidence and is itself hashed. The log may contain original machine paths and is not sanitized for sharing.

Source content is hashed before and after extraction; file identity/stat changes cause rejection. Source symlinks are rejected. These are integrity checks, not protection from malicious concurrent mutation.

The destination must not exist. Inside this repository it must be under output/visual_evidence*; normal production export directories are rejected. A new external destination is also supported. All files and the completed manifest are staged in a temporary sibling directory, then the directory is renamed into place. Errors/timeouts clean only that staging directory. An empty newly created parent may remain. No existing output is deleted, repaired or overwritten.

The implementation targets the existing Windows workflow. No concurrent writers or whole-bundle power-loss durability guarantee is provided. Frame extraction times out after 600 seconds; each crop after 60 seconds. Very long sources or many crops may require a smaller explicit range or frame limit.

## Validation performed

    python -m unittest test_visual_evidence -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Synthetic validation only:

- Three-second 160x90, 4 FPS fixture; requested start 0.3, end 2.1, interval 0.5, cap 3.
- Measured frames at 0.5, 1.0 and 1.5 seconds; independently matched to FFprobe decoded-frame PTS.
- 80x46 frame output plus 12 crops: full 80x46, top-center 40x12, bottom-left 40x17, bottom-center 40x12 per frame.
- Actual CLI smoke test on a gapped/variable-rate source beginning at PTS 3.0 seconds; normalized samples 0.5, 1.0, 1.5 matched decoded PTS minus the first frame. Unknown game correctly used generic extraction.
- Temporary sources and outputs removed. No production frame extraction, model inference or OCR ran.

Unit tests cover profile/geometry validation, bounds/caps, deterministic naming, hashes and relative paths, source conflicts/mutation, empty outputs, PTS parsing, failures/publication, overwrite protection and import safety. The synthetic integration test requires FFmpeg/FFprobe and reports a skip explicitly if absent.
