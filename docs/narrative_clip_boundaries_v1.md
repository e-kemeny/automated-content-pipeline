# Experimental Narrative-Aware Clip Boundaries V1

This read-only planner suggests boundaries from saved evidence. It is not a narrative detector, export command, or validated editing policy. No models, media probes, OCR, encoding or production changes occur.

## Usage

```powershell
python narrative_clip_boundaries.py --analysis output/shared_analysis_v1.json --output output/narrative_boundaries.json
python narrative_clip_boundaries.py --analysis output/shared_analysis_v1.json --annotations output/gameplay_events.json --fusion output/event_fusion.json --timeline output/timeline.json --min-duration 1 --max-duration 60 --max-extension 10 --output output/narrative_boundaries_review.json
# Explicit heuristic-only fallback (optional):
python narrative_clip_boundaries.py --analysis output/shared_analysis_v1.json --heuristic-padding 3 --output output/narrative_padding.json
python -m unittest -q test_narrative_clip_boundaries
```

Optional input paths are examples; they must name existing artifacts. Output must be new; there is no overwrite flag. Repository outputs belong under ignored output/. Existing atomic publication rejects input aliases and existing destinations.

## Deterministic policy

1. Validate Shared Analysis V1 and preserve every candidate row, index, score, metadata and provenance. No reordering, deduplication or selection.
2. Human inputs must be the existing gameplay-event-annotations V1 template for exactly these source claims, candidates and provenance. Only an explicitly **certain**, **exact_interval** annotation attached to this candidate and overlapping its original window can support expansion.
3. Exactly one such interval permits expansion to encompass it. Multiple eligible intervals are ambiguous: keep the baseline. Events are never chained by proximity or matching labels. A complete contained interval needs no change.
4. Clip-level bounds, points, uncertain annotations, transcript speech intervals and OCR/fusion observation envelopes never supply precise gameplay boundaries. Existing fused V1 groups explicitly have null gameplay event intervals. They and timeline rows are preserved as review context.
5. With no eligible interval, explicitly enabled fixed padding can suggest expansion, labeled heuristic_only. It is not evidence of semantic context or resolution.
6. Reject a whole expansion if either side exceeds maximum extension or the resulting duration exceeds limits. Never cut off part of a supported interval to fit. Reject expansions whose added footage overlaps other human events or source-clock fused groups; uncertain evidence is conservatively a blocker, not a precise boundary.
7. Original windows remain unchanged when evidence is insufficient or a proposal is blocked. No shrinking occurs. Padding clamps to [0, source duration]. Half-open overlap semantics reuse fusion utilities; mere endpoint touches do not link events.

Defaults: minimum duration 1 second, maximum duration 60 seconds, maximum extension 10 seconds per side; padding disabled. These are explicit experimental safety limits, not tuned parameters. If original windows already violate the requested duration limits, planning fails rather than silently altering the baseline. Source duration comes from saved analysis; invalid or out-of-bounds inputs fail validation.

No game-specific rules are used. The existing annotation vocabulary, including other, is accepted without interpreting particular game mechanics.

## Output and identity

Schema version 1, artifact_type narrative-clip-boundaries. Inputs are retained in full with canonical JSON digests, explicit missing/provided availability, source claims, configuration and deterministic plan_id. Each candidate retains original_candidate and a stable identity derived from index/source/row, plus proposed start/end/duration, changed, status, reason, supporting_event_id, blocked_by, and original human events. Generated candidate IDs are local to this plan schema; existing IDs remain in original_candidate.

Statuses: evidence_supported (including already complete intervals), heuristic_only, insufficient_evidence. A supporting_event_id records the considered support even when limits/blockers reject its proposal; inspect status and changed together.

Timeline context reuses candidate_evidence. Fused artifacts are reconstructed with the existing pure fusion producer and compared completely, rejecting altered schemas, groups or provenance. Its lightweight saved-text checks do not run external inference. Cross-artifact linking requires consistent reported SHA-256 claims; mismatches fail. Existing annotations require the exact analysis template, intentionally stricter than relocation identity.

This planner does not verify live video bytes or duration. Human timing is a reviewed claim, not independently measured truth. Missing evidence remains unknown. Conservative blocking can reject useful expansions, and exact human intervals may be unavailable; unchanged output is an expected result. No improvement in narrative quality is claimed.

## Synthetic examples

For original [2,10), a candidate-linked certain exact event [1,4) proposes [1,10); [8,12) proposes [2,12); [4,8) leaves [2,10) unchanged. Clip-level [1,12) leaves the baseline unchanged. These are unit-test examples, not inferred gameplay results.
