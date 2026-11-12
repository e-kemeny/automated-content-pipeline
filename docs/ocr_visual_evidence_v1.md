# Game-Agnostic OCR Visual Evidence V1

A separate, standard-library OCR consumer for previously extracted PNG evidence. It does not decode videos, change the visual extractor, identify games, classify gameplay events or update production analysis/ranking. OCR observations remain separate from human ground truth and the multimodal timeline.

## Availability on the development laptop

Inspection found no Tesseract or ocrmypdf executable on PATH, and no Tesseract executable in the checked Program Files / LocalAppData Tesseract-OCR locations. pytesseract, EasyOCR and PaddleOCR package metadata was absent. Pillow 12.3.0 and NumPy 2.5.1 were present but are not required or imported by this stage.

**No real OCR recognition ran.** Success/no-text/parser cases use injected fake backends or mocked Tesseract TSV. The actual CLI diagnostic returned unavailable with version null and exit code 1. No dependencies, executables or language data were installed or downloaded.

## Commands

The actual extractor manifest filename is visual_evidence_manifest.json:

    python ocr_visual_evidence.py --check-backend
    python ocr_visual_evidence.py --check-backend --executable path/to/tesseract.exe --language eng

    python ocr_visual_evidence.py --manifest output/visual_evidence_v1/visual_evidence_manifest.json --output output/ocr_visual_evidence_v1.json --backend tesseract --mode both

--mode supports full, crops or both (default). --executable selects an already installed Tesseract executable; otherwise PATH discovery is used. --language and --psm override profile hints. --overwrite is explicit and limited to the same OCR artifact type/version. No executable or model is installed automatically.

To enable real OCR later, separately provision a trusted Tesseract installation with the required language data, expose its executable through PATH or --executable, and run --check-backend. That check verifies executable/version and requested language availability, not actual OCR quality or successful recognition. Then validate a small known text image before processing gameplay crops. Do not assume installing a Python wrapper supplies the native engine.

## Backend interface

An injected backend has an identifier plus:

- check(language): metadata containing identifier, version, status (available/unavailable/failed) and reason where relevant.
- recognize(image_path, language, psm): text and a words list; words preserve text, optional bbox and optional native confidence.

The built-in Tesseract adapter uses --version, --list-langs and a subprocess recognition command with stdout output and TSV configuration. No arbitrary configuration flags or shell commands are accepted. Version/language probes time out after 10 seconds; recognition after 60 seconds.

The [official Tesseract CLI documentation](https://tesseract-ocr.github.io/tessdoc/Command-Line-Usage.html) describes language/page-segmentation options and TSV output. The adapter preserves TSV word text, boxes and reported confidence. The convenience text field joins words by TSV line identifiers; it is not a reconstruction of the original typography. A confidence of -1 means absent and is omitted, not replaced with zero. Reported confidence remains on the engine's 0-100 scale, not a calibrated probability.

Malformed TSV, nonfinite/out-of-range confidence, invalid boxes or backend exceptions produce failed observations with null text/words and an error. Other injected adapters must follow the documented text/words contract; this is not a plugin registry.

## Input validation and paths

The consumer reads Visual Evidence V1's source identity, duration, sampling configuration, profile, frames, crop rows, measured normalized_pts/time_base/timestamp_seconds, extraction provenance and coverage. It validates the supported schema, source duration agreement, producer frame IDs, timestamp ordering/arithmetic, sampling bounds, crop parent/geometry and dimensions.

All referenced image paths must be relative to the manifest directory. Absolute paths, drive-relative paths, traversal, backslash paths, alternate-stream syntax, symlink/junction components and paths escaping that root are rejected. Nested forward-slash relative paths are supported.

Every referenced frame and crop is checked against its SHA-256 and PNG dimensions **before backend recognition**, even when excluded by the requested mode. Missing/modified images fail closed; they are not silently treated as empty OCR. Manifest and image hashes/metadata are checked again after recognition. Source video bytes are not read: source identity remains a preserved manifest claim, not a new independent video verification.

Output publication uses the existing atomic JSON helper. Inputs and aliases cannot be overwritten, and unrelated artifacts remain protected even with --overwrite. OCR writes only the requested report and temporary publication file in its parent directory; the subprocess sends recognition output to stdout. No input manifest/image is changed. No concurrent writers or malicious executable/filesystem mutation guarantees are made.

## Full frames, crops and optional profiles

Ordering is frame order, then full image followed by its crops in manifest order. Each observation retains a stable ID, parent frame ID, image/crop metadata, measured timestamp, region name and image path/hash. Crop boxes are in **crop-image pixels**, not translated parent-frame coordinates; the preserved pixel_rectangle allows a future explicit mapping.

Identical image bytes, dimensions and OCR settings reuse one result within the invocation. The repeated observation remains present with reused_from pointing to the first observation. This can avoid processing a full-frame crop twice without losing relationships. Reuse includes unavailable/failed outcomes and never constitutes persistent inference caching.

No crops in crop-only mode yields no_inputs, zero observations and an explicit reason, not successful empty-text recognition.

The core has no game-specific rules. Generic, BedWars and unknown/custom game profiles use the same backend. Optional hints may be set in a **new custom extraction profile before extraction**, without rewriting saved manifests:

    "ui_hints": {
      "ocr": {
        "language": "eng",
        "psm": 6,
        "preferred_regions": ["top_center"]
      }
    }

Only language, psm and preferred_regions are supported inside ocr; invalid hints fail. Defaults are eng and PSM 3. PSM 3-13 is accepted; orientation-only modes are excluded. Preferred regions filter crops, not full frames. An empty preferred list selects no crops. Other UI hints are preserved as provenance and never used to fabricate expected text or events.

## Output and statuses

The version-1 ocr-visual-evidence artifact records backend/version, mode/settings, source identity, a digest and full provenance copy of the visual manifest, observations, counts, coverage and limitations. It embeds no image bytes.

Per-image statuses:
- text_found: successful recognition with nonblank text.
- no_text: successful recognition with no text.
- unavailable: engine/language unavailable; text and words are null.
- failed: backend execution or output validation failed; text and words are null.

Overall status is completed, partial, unavailable, failed or no_inputs. CLI exit code is nonzero for partial/unavailable/failed runs even though the diagnostic report is saved; completed and no_inputs return zero. Malformed inputs, hash mismatches or publication failures return nonzero without a new report. --check-backend prints diagnostics without writing a report.

Frame timestamps retain the extractor's first-decoded-video-frame origin. They locate visual observations, not gameplay events, and are not silently aligned to transcript/audio clocks. Missing OCR, sparse sampling and no-text results do not establish absence of gameplay events or UI text. No confidence aggregation or gameplay scoring occurs.

## Validation

    python -m unittest test_ocr_visual_evidence -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Synthetic valid PNG bundles and injected backends cover text/no-text/unavailable/failure, confidence/boxes, modes/reuse, missing crops, paths/hashes, identity/timing, profile hints, deterministic output, atomic publication and import safety.

The actual unavailable-engine CLI smoke test produced two unavailable observations (full frame and crop), null text/words, and exit code 1. Input hashes and nanosecond mtimes stayed unchanged; temporary fixtures were removed. A real synthetic text-image recognition test could not run because no supported OCR engine was found. This limitation is not counted as OCR success.
