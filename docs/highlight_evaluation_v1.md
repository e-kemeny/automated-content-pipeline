# Experimental Highlight Evaluation V1

Offline descriptive comparison of existing candidate scores and manually supplied
human ratings. This is not a replacement selector, training step, or production
ranking change. Standard library and existing validators only.

## Workflow

Generate a template from an existing Shared Analysis V1 artifact:

    python highlight_evaluation.py template --analysis output/shared_analysis_v1.json --output output/highlight_ratings_v1.json

Watch the candidate clips and edit only each candidates entry's human_rating.
Every rating starts as null. Use integer ratings:

| Rating | Suggested interpretation |
| --- | --- |
| 1 | Not worth retaining |
| 2 | Weak; substantial trimming/context needed |
| 3 | Usable with editing |
| 4 | Strong highlight |
| 5 | Standout highlight |

Choose a consistent viewing context and apply the same rubric to every clip.
Leave unseen/uncertain entries null; null is missing, never zero. This V1 format
supports one supplied rating per candidate, not multi-rater reliability analysis.

Evaluate later:

    python highlight_evaluation.py evaluate --analysis output/shared_analysis_v1.json --ratings output/highlight_ratings_v1.json --output output/highlight_evaluation_v1.json

Optional Candidate Evidence V1 context:

    python highlight_evaluation.py evaluate --analysis output/shared_analysis_v1.json --ratings output/highlight_ratings_v1.json --evidence output/candidate_evidence_v1.json --output output/highlight_evaluation_v1.json

Evidence must match the candidate rows, source claims and selection provenance.
Its original input provenance, identity status, counts and coverage are retained
as context; none enters a quality score or modifies ratings.

## Supported schema and binding

Uses the actual Shared Analysis schema_version 1 candidate_windows envelope.
Rows use start/end in source seconds, optional second, original scores and other
metadata. They must already be analyzed and chronological under existing rules.
No fields are inferred from logs or export filenames.

Template schema_version=1, artifact_type=highlight-ratings contains source claims,
selection provenance, analysis schema version, rating scale, candidate-set digest,
and candidates. Every entry contains original position, a deterministic content
ID, boundaries, full original candidate, selected score key/value/comparability,
and human_rating. IDs do not treat stored positions as ranks.

The candidate-set SHA-256 binds canonical JSON of source claims, analysis schema
version and the entire original candidate envelope. Candidate IDs bind source
claims and each original row. These are metadata fingerprints, not video hashes
or cryptographic signatures. They detect mismatched templates relative to the
supplied analysis, not deliberate edits to both analysis and template.

Evaluation regenerates the template and requires all fields except human_rating
to agree. Unsupported versions, changed IDs/order/boundaries/scores/provenance,
wrong counts, invalid ratings and duplicated windows fail. Duplicate start/end
windows are rejected even if their metadata differs, to avoid ambiguous repeated
human assessments. An analyzed empty candidate list is supported.

Source path is informational and can change after relocation; all non-path source
claims must remain identical. SHA-256 claims are validated but never independently
rehash video. Missing source digest is explicitly unverified_missing_source_digest;
available digests are reported_sha256_unverified. Neither label proves content
identity. Missing metadata is not silently filled from ratings or filenames.

## Ranking comparability and metrics

Stored order is chronological, not a ranking. For a uniform fixed-detector
artifact, the existing provenance maps score fields as follows:

- Audio-only: score
- Audio + Scene: highlight_score
- Audio + Motion: motion_highlight_score

Only selected_windows (including the established implicit default) and
candidate_pool representations qualify. Unknown detector/variant/representation
prevents score comparison. A missing/non-numeric score or a contradictory
row-level detector makes that row incomparable. Nonfinite JSON values fail.
No user override permits inventing score comparability. Comparisons are
conditional on producer provenance accurately describing a common source/run
and score definition; this tool cannot independently verify that provenance.

Outputs include total/rated/unrated counts, arithmetic mean of available ratings,
unchanged original candidate order, human-preferred order among rated candidates,
and original score order among comparable candidates. Both preference orders
are descending lists of explicit tie groups, preserving stored order within ties.
These are inspection summaries, not new production selections.

Every unordered candidate pair receives exactly one status:
unrated, incomparable, original_tie, human_tie, both_tied, agree or disagree.
Unrated pairs are classified first; incomparable applies to rated pairs lacking
comparable scores. Exact equality defines ties; no tolerance is invented.

Strict pairwise agreement = agree / (agree + disagree).
Only pairs with two ratings, two comparable scores and no ties enter this
denominator. The denominator and all excluded categories are reported.
With no eligible pairs the result is null, never zero or perfect agreement.

Each candidate lists counterpart indices for strictly discordant pairs.
A score preference and opposite human preference is a disagreement; chronological
position is never used as a quality preference. Pair details and candidate rows
make the result inspectable without inventing a rank displacement for ties.

Report schema_version=1, artifact_type=highlight-evaluation preserves candidate
records, human ratings, source claims, input provenance, a canonical ratings
digest, metrics, pair statuses, optional evidence context and limitations.
All results are descriptive and exploratory. Tiny preselected samples cannot
establish generalization, significance, accuracy, precision/recall or correlation.
The mean of this ordinal rubric is a descriptive summary, not calibrated quality.
Selection bias and missing ratings must accompany interpretation.

## Output safety

Outputs are deterministic sorted-key JSON, using the existing atomic writer.
An existing destination is refused unless --overwrite is explicit; only artifacts
of the same type/version may then be replaced. Recreating a template with
--overwrite resets its ratings to null: do not do that to preserve completed work.
Inputs, aliases, symlinks and unrelated artifacts cannot be overwritten.
Inside the checkout, output must be under ignored output/; external paths are
allowed. Inputs are never changed.

Exclusive publication uses a flushed/fsynced temporary sibling and a hard link;
explicit overwrite uses atomic replacement. Unsupported hard-link filesystems
fail safely. Temporary files are cleaned after ordinary failure; an empty newly
created parent directory may remain. Concurrent overwrite writers are unsupported.

Exit codes: 0 success, 1 validation/I/O failure, 2 CLI misuse.
No source-media processing, FFmpeg, model loading or inference occurs.

## Real artifact validation, 2026-11-07

An in-memory template was generated from the existing saved Shared Analysis.
All original rows and scores were preserved; all five human ratings remained null.
No production rating/evaluation artifact was written and no clips were rated.

| Index | Window (seconds) | Original Audio-only score | Human rating |
| --- | --- | --- | --- |
| 0 | 30–45 | 5774.281875 | null |
| 1 | 59–74 | 6411.09445 | null |
| 2 | 74–89 | 8945.897975 | null |
| 3 | 136–151 | 6532.2561375000005 | null |
| 4 | 160–175 | 8375.8160375 | null |

Original order is [0,1,2,3,4]; descending existing score order is [2,4,3,1,0].
No human preference exists yet: rated=0, unrated=5, mean=null, agreement=null;
all ten pairs are unrated. Identity is reported_sha256_unverified.

Full Observation Persistence has only been validated on synthetic media.
This workflow neither assumes a production full-observation artifact exists
nor requires one.

## Tests

    python -m unittest test_highlight_evaluation test_shared_analysis test_candidate_evidence test_inspect_candidate_evidence -q
    python verify.py --cached-export --video videos/my_recording.mp4 --analysis output/shared_analysis_v1.json

Synthetic ratings appear only in unit-test fixtures, never in real artifact
validation.
