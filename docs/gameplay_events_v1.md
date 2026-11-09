# Gameplay Event Ground Truth V1

A standalone human annotation layer for future gameplay-event research. It does not detect events, score highlights, alter boundaries, or write into Shared Analysis or existing Ground Truth V2. Audio spikes, scene changes, transcripts and generic ImageNet predictions do not reliably recognize BedWars events. No media is opened, hashed or processed by this CLI.

## Workflow

From the repository root:

```powershell
python gameplay_events.py template --analysis output/shared_analysis_v1.json --output output/gameplay_events_template_v1.json
# Copy the template to gameplay_events_v1.json and manually add reviewed events.
python gameplay_events.py query --annotations output/gameplay_events_v1.json --start 30 --end 45
python gameplay_events.py align --annotations output/gameplay_events_v1.json --timeline output/multimodal_timeline_v1.json --output output/gameplay_event_alignment_v1.json
```

`query` and `align` print JSON and accept optional `--output`. Output publication is atomic using the existing helper. Existing files require explicit `--overwrite`, which only permits the same artifact type/version. Inputs, symlinks and unrelated artifacts are protected. In-repository outputs must be under ignored `output/`. Avoid concurrent writers. Template overwrite deliberately resets annotations: use a separate template filename and retain your human-edited copy.

## Schema and precision

The versioned document has `schema_version: 1`, `artifact_type: gameplay-event-annotations`, `analysis_schema_version`, `source_video_identity`, `candidate_provenance`, `template_id`, and `candidates`. Each candidate contains its original `candidate_index`, complete `original_candidate` row, and an initially empty `events` list. The actual Shared Analysis rows use `start`, `end`, `second`, `duration`, `score`, and additional audio/visual scores. All are preserved. The current five candidates are preselected Audio-only windows, not a newly ranked pool. Order and duplicate windows are retained.

`template_id` fingerprints the original template; only event lists may be edited. It detects accidental changes to original candidates/claims/provenance, not malicious tampering or authorship. Regenerate a template to adopt different candidates. Events retain entered order within each candidate; nothing is sorted or deduplicated.

Required event fields:

| Field | Meaning |
| --- | --- |
| `event_id` | Nonempty user-assigned identifier, unique throughout the document |
| `event_type` | `fight`, `player_elimination`, `player_death`, `bed_destroyed`, `game_victory`, `game_transition`, `respawn`, or `other` |
| `start_seconds`, `end_seconds` | Finite nonnegative source-video seconds, start <= end |
| `temporal_precision` | One of the three conventions below |
| `description` | Nonempty human description |
| `source` | Exactly `human`; model predictions are rejected |
| `source_video_identity` | Copy of the document's identity envelope, including its unverified status |
| `provenance` | Object requiring nonempty `annotator` and `method: manual_review`; other JSON provenance is retained |

Optional fields: `certainty` is null/omitted, `uncertain`, or `certain` (human certainty, not a calibrated probability); `player` and `team` are JSON objects; `notes` is text. No certainty is generated. Unknown event fields, invalid metadata, NaN/infinity, duplicate JSON keys and unsupported schema versions fail.

- `exact_point`: start == end, a human-specified instant. Exact means the annotation asserts a precise time, not that the software verified it.
- `exact_interval`: start < end, human-specified event extent.
- `clip_level`: start < end, an uncertainty range containing the described occurrence somewhere. It does **not** mean continuous action, exact onset/end, event count or ordering inside that range.

Candidates provide review context, not a constraint requiring all later annotations to stay inside their windows. A human may inspect additional footage and annotate broader timing explicitly. All times must satisfy the source duration claim. Queries use **closed** `[start,end]` overlap, consistent with Timeline Query V1: touching boundaries and point queries match, including the final endpoint. Adjacent queries can retrieve the same event; this is retrieval, not an exclusive evaluation assignment. Distinct IDs with otherwise identical annotations remain separate.

## Entering a coarse annotation

Documentation-only example for candidate 0, based on the user's coarse report of a bed break somewhere in 30-45 seconds. This does not locate the break or assign its duration. Nothing below is run by template generation:

```python
from copy import deepcopy
from gameplay_events import validate_annotations
from multimodal_timeline import read_json
from highlight_evaluation import publish

document = read_json("output/gameplay_events_template_v1.json")
document["candidates"][0]["events"].append({
    "event_id": "review-clip0-bed-observation",
    "event_type": "bed_destroyed",
    "start_seconds": 30,
    "end_seconds": 45,
    "temporal_precision": "clip_level",
    "description": "A bed break was reported somewhere in this reviewed clip; exact timing is unknown.",
    "source": "human",
    "source_video_identity": deepcopy(document["source_video_identity"]),
    "provenance": {"annotator": "replace with reviewer identifier", "method": "manual_review"},
    "notes": "Coarse clip-level report only; no frame-level annotation."
})
validate_annotations(document)
publish(document, "output/gameplay_events_v1.json", ["output/gameplay_events_template_v1.json"])
```

Use `player_elimination` for an observed elimination, `player_death` for an observed death, and describe whose perspective is known in optional player/team details. Do not infer exact counts, team identity or event sequence when the review did not establish them. These categories describe human claims, not automatic predictions.

### Existing user observations (context only)

| Reviewed clip | User's coarse observation |
| --- | --- |
| 30-45 s | Multiple fights and a bed break. |
| 59-74 s | Fight against an aqua player. |
| 74-89 s | Fight resolution, defending a bed, killing an attacker, destroying a bed, and winning a game. |
| 136-151 s | Encounter involving an invisible player. |
| 160-175 s | Introduction to another game, fight, player death, opponent moving toward the bed. |

These are approximate clip-level reports, not exact timestamps or frame-level ground truth. They are not automatically inserted into any template or assigned confidence scores. An empty event list means unannotated, not “no event occurred.”

## Source identity and duration

`source_video_identity` contains `claims` (original source metadata, including location) and `status`: `reported_sha256_unverified` when a valid digest is present, otherwise `unverified_missing_source_digest`. A matching reported digest is never proof of live source content. Annotation/query works with a missing digest but reports that limitation. Event claims must match the document; conflicting source digest/duration provenance is rejected across events and candidate provenance. Missing, zero, negative or nonfinite source duration fails closed. The reported duration is used only as an internal consistency bound, not represented as independently measured here.

The reusable `validate_annotations(document, verified_source=...)` can additionally check independently verified source metadata supplied by a trusted caller. It requires matching SHA-256 and duration, checks shared identity fields and enforces those bounds. Do not pass document claims as if independently verified. The CLI has no verified-source flag and never promotes saved status; this milestone performs no video verification or processing.

## Optional timeline alignment

`align` validates both inputs and requires consistent reported SHA-256 on the annotation header and **every** timeline artifact. Missing digests or explicit conflicts fail instead of associating possibly unrelated videos. Paths are informational; matching claims remain unverified.

For each human event, the existing timeline query retrieves overlapping audio, scene, transcript and supported vision observations. Original event precision/provenance, observation payloads, timeline source records and duplicates are retained. Modality availability uses existing coverage reporting; continuous temporal coverage remains `unknown`. An empty match is not proof that an event was absent. A `clip_level` match spans the uncertainty range, not a known event duration. ImageNet predictions keep their original labels. Overlap is neither causality nor classifier accuracy; no scoring, semantic inference or boundary changes occur.

## Testing and limits

```powershell
python -m unittest test_gameplay_events -q
python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json
```

Tests use synthetic JSON fixtures and isolated import checks, not production video or models. The format records human claims and consistency; it cannot prove a human watched the video, authenticate provenance, verify timestamp accuracy or resolve disagreement between annotators. Future detection/evaluation must preserve these uncertainty distinctions rather than treating coarse windows as precise labels.
