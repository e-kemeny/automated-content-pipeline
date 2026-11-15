# Experimental Multimodal Event Fusion V1

This optional, standard-library stage groups saved hypotheses for human review. It does not confirm gameplay events, assign confidence, run OCR/ASR/models, or change highlight selection.

## Usage

```powershell
python multimodal_event_fusion.py --transcript output/transcript_events.json --ocr output/ocr_interpretation.json --timeline output/timeline.json --output output/event_fusion.json
python -m unittest -q test_multimodal_event_fusion
```

Paths above are examples; use your existing artifacts. At least one input is required by the CLI. The Python interface is `fuse_events(transcript=..., ocr=..., timeline=...)`. Existing output files cannot be replaced. Publication reuses the project's atomic, exclusive JSON writer; inputs are never modified.

## Schema and validation

Output has `schema_version: 1` and `artifact_type: "multimodal-event-fusion"`.

- `source_identity` contains the existing reconciliation result: identity status, reported content identity, and duration.
- `inputs` retains complete input documents; `input_digests` records canonical JSON digests.
- `modalities` explicitly distinguishes missing from provided inputs. `coverage` preserves producer coverage and OCR observation statuses. Temporal coverage remains unknown.
- `alignment` records any caller-supplied clock mapping; `policy` records aliases and overlap rules.
- `groups` contains original evidence, references, detection methods, modality, original/canonical labels, alignment intervals, uncertainty, counts, and source agreement.
- `context_observations` retains timeline rows; group context references do not contribute to semantic evidence counts.
- `duplicate_references` records exact duplicates excluded from counts.

Only existing V1 transcript-event, OCR-interpretation and timeline schemas are supported. The adapters validate provenance, source consistency, original intervals, embedded OCR frame/crop records, and producer contracts. Lightweight existing phrase rules are replayed against saved text for validation. No external inference is invoked. When a timeline accompanies transcript hypotheses, its canonical digest must match their recorded input digest.

Multiple sources require matching reported SHA-256 identities and consistent metadata. Conflicts fail. This checks claims, not source video bytes or authenticity: no source video/images are opened, and embedded manifest hashes cannot authenticate unavailable original files.

## Time and semantic rules

Transcript timestamps bound speech, not confirmed gameplay events. OCR timestamps are relative to the first decoded video frame. These clocks are kept separate by default, even for the same video.

To align OCR with the timeline, supply both `--ocr-time-offset-seconds OFFSET` and `--alignment-reference "explanation of verified mapping"`. Aligned time is original OCR time plus OFFSET. Do not assume zero; establish the mapping independently. Original timestamps are retained and out-of-bounds mappings fail.

Intervals are half-open: [start, end). Points overlap an interval only inside it; equal points overlap; touching interval endpoints do not. This is an explicit fusion policy, separate from candidate-evidence query boundaries.

Grouping requires identical canonical labels, the same clock, and overlap between every pair of members. Stable greedy assignment avoids transitive overlap chains. Generic aliases are game_victory/victory, player_death/death, player_elimination/kill, and game_transition/transition. Specific objectives are not collapsed into generic objective events. Unknown-game fallback and custom OCR profile metadata are preserved; fusion does not detect a game.

Exact duplicate records count once; different crops/frames may still be correlated. Chronological ordering is within each clock; no cross-clock chronology is asserted. Ambiguous associations are deterministic review groupings, not proof that observations refer to one event.

## Synthetic example and limitations

With explicitly aligned clocks, a victory speech hypothesis over [0, 2) and an OCR victory hypothesis at 0.5 can yield:

```json
{
  "event_type": "victory",
  "status": "hypothesis_evidence_group",
  "evidence_count": 2,
  "hypothesis_modalities": ["ocr", "transcript"],
  "source_agreement": "cross_modality_label_overlap",
  "observation_envelope": {"start_seconds": 0, "end_seconds": 2},
  "gameplay_event_interval": null
}
```

This excerpt is synthetic, not a gameplay benchmark. Full groups also retain members and references. The envelope describes observations only. Missing OCR, failed OCR, empty text and zero matching phrases are not negative evidence. Timeline audio/visual observations supply temporal context, not semantic corroboration. No confidence percentages, event ranking, or production integration are implemented.
