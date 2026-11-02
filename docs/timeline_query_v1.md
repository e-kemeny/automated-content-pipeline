# Timeline Query V1

Retrieve persisted observations for future highlight evidence retrieval. No inference, scoring, ranking, deduplication, or media processing occurs. The existing timeline validator and schema are reused unchanged.

## Usage

    python timeline_query.py --timeline output/multimodal_timeline_v1.json --start 45 --end 60
    python timeline_query.py --timeline output/multimodal_timeline_v1.json --start 45 --end 60 --modality visual
    python timeline_query.py --timeline output/multimodal_timeline_v1.json --start 45 --end 60 --output output/timeline_query_v1.json

Filters: visual, audio, transcript. Omit to include all modalities.
Stdout is compact JSON, including when saving a file. Errors go to stderr with nonzero status.
Use --overwrite with --output to explicitly replace an existing result. The input timeline cannot be replaced.

## Time and validation

Queries use closed [start, end] intervals. Points match when start <= time <= end.
Intervals match when event_start <= query_end and event_end >= query_start.
Boundary-touching intervals count; zero-length queries are valid.

Query timestamps must be finite numbers (not booleans), nonnegative, ordered, and within video duration when known. Unknown duration imposes no upper bound. Invalid timelines, unsupported versions, malformed events and unsorted stored events are rejected, even if the offending event would not match. No clamping or reordering occurs.

## Result

- query: start_seconds, end_seconds, modality (null if unfiltered)
- timeline_schema_version: original version
- identity_status and source_identity: unchanged identity claims
- sources: unchanged artifact/channel provenance, preserving event references
- matched_event_count
- counts_by_modality: audio, visual, transcript, including zeros
- events: exact copies of matching objects in stored order

Repeated observations remain separate. No matches produces an empty events list and zero counts. Returned mutable objects are independent copies; input is not modified.

Identity status is copied without upgrading trust: reported hashes are not independently verified against video bytes. No gameplay labels, confidence values, quality scores or semantic relationships are inferred.

## Persistence and limitations

No file or directory is created unless --output is supplied. Publication uses a flushed sibling temporary file and atomic replacement (explicit overwrite) or exclusive hard-link publication (no overwrite). Failures clean up temporary files and preserve existing destination contents. A newly created empty parent directory may remain after failure. Filesystems without hard-link support reject exclusive publication rather than using an unsafe fallback.

Do not use concurrent overwrite writers. --overwrite authorizes replacing the chosen destination; select a query output path, not another artifact. No FFmpeg, CUDA, model weights or third-party Python packages are required. Results are retrieval evidence only, not highlight selections.
