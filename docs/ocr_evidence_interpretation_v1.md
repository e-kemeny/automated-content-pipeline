# OCR Evidence Interpretation V1

Experimental, standard-library-only phrase matching over saved OCR evidence.
This is not semantic understanding or confirmed gameplay-event detection. It
does not run OCR, load models, read images/video, or affect production ranking,
boundaries, candidate selection, or exports.

## Usage

From the repository:

    python ocr_evidence_interpretation.py --input output/ocr_visual_evidence_v1.json --output output/ocr_interpretation_v1.json
    python ocr_evidence_interpretation.py --input output/ocr_visual_evidence_v1.json --output output/ocr_interpretation_bedwars_v1.json --game bedwars

Input must be an existing OCR evidence artifact; no actual OCR results are
invented or supplied by this milestone. Output must be new; there is no overwrite
flag. Repository outputs must remain under ignored output/. Input/output aliases
are rejected using the existing publication helper.

The generic defaults match "victory", "you died", "eliminated", and
"objective completed". Explicit --game bedwars adds "bed destroyed" and "final
kill". Unknown games use generic defaults and record unknown_game_fallback=true;
the tool never infers a game from the image, OCR text, or extraction profile.

Built-in phrases live in profiles/ocr_interpretation_generic_v1.json and
profiles/ocr_interpretation_bedwars_v1.json; the matching algorithm contains no
game-specific phrases or branches.

Use --profile path/to/profile.json instead of --game for a custom vocabulary:

    {
      "schema_version": 1,
      "name": "example",
      "patterns": [
        {"id": "capture", "event_type": "objective", "phrase": "point captured"}
      ]
    }

Phrases are literal, case-insensitive, bounded by non-word characters, and allow
one or more whitespace characters between words (including OCR line breaks).
They are not arbitrary regular expressions. Pattern IDs must be unique.
Custom profiles replace the defaults; event_type is a configurable hypothesis
label, not a write into the semantic-events timeline.

## Contract and limitations

interpret_evidence(evidence, game="generic", profile=None) returns version-1
ocr-evidence-interpretation JSON. input_evidence is an unchanged deep copy of the
entire original artifact: source identity, backend/version, provenance, measured
timestamps, observation/parent-frame IDs, region names, image/crop metadata,
engine word confidence and failures all remain available. The current producer
identifies crops through observation_id, parent_frame_id and region_name; this
module invents no crop identifier. Extra producer metadata is also retained.

interpretations links to observations by observation_id, retaining input order.
Matches retain the original text substring and zero-based [start,end) character
offsets, pattern ID, event type and status="hypothesis". Multiple matches are
sorted by text position and then pattern ID. Full-frame/crop duplicates and
repeated frames are not merged. There is no hypothesis confidence or quality
score; OCR confidence is not repurposed.

Per-observation statuses distinguish hypotheses, no_match, no_text, ocr_failed
and ocr_unavailable. API input None (or a JSON null input) yields not_analyzed;
an empty observations list yields no_observations. A missing file fails clearly.
Top-level interpreted means the interpretation pass completed, not that OCR was
available or any event occurred.

Unsupported versions, invalid source identity, duplicate observation IDs,
nonfinite/inconsistent/out-of-order/out-of-bounds timestamps, malformed profiles,
invalid OCR confidence and inconsistent text/status fail validation. Equal
timestamps are allowed for multiple observations of the same frame. Validation
covers consumed fields, not independent authentication of the embedded source
video, image hashes or all producer provenance. No files referenced inside OCR
evidence are opened. The input digest is canonical JSON, not a raw-file checksum.

False positives include negations ("not a victory"), chat, tutorials, quoted
notifications and OCR mistakes. No match does not imply no event. Sparse frame
timestamps retain the producer's time basis and are not event onset/end times.
Patterns are an unvalidated review aid, not contextual language scoring.

## Verification

    python -m unittest -v test_ocr_evidence_interpretation
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Tests use synthetic producer-shaped OCR data and a fake backend only to construct
fixtures. They require no Tesseract installation, model, download, or real OCR.
Real gameplay recognition accuracy has not been measured.
