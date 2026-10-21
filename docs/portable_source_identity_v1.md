# Portable Source Identity V1: design and compatibility contract

Status: DESIGN ONLY, 2026-10-21. No production reader, schema, cache rule or
migration changes. V1 in this title is the design iteration; the proposed
wire format uses manifest_version 2 with source_identity.version 1.

## Current evidence and behavior

The real Shared Analysis schema is 1; both export manifests are version 1.
All three contain the same source full-file SHA-256:
6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09.
The source duration is 231.433288 seconds. Analysis uses a relative locator;
manifests store a resolved absolute source path plus dimensions/FPS.
transcription.media_sha256 hashes the entire file, not a filename or sample.

Thus existing recorded digests are sufficient reference evidence to verify
relocated bytes under the usual SHA-256 integrity assumption. No new digest
algorithm or historical source digest is needed for these artifacts. The supplied
file must still be read and hashed during verification; trusting a copied digest
string alone proves nothing. No new production-video hashing is added here.

Current export planning compares actual source hash/duration against analysis.
Strict cache-only compares the entire manifest source record, including path.
Both manifest versions require source identity, unchanged raw analysis hash,
matching selection/plan/encoding, successful records and intact playable outputs.
See artifact_relocation_audit.md for exact current errors and path behavior.

## Proposed manifest fragment (not an implemented schema)

    {
      "manifest_version": 2,
      "source_identity": {
        "version": 1,
        "algorithm": "sha256",
        "digest": "<64 lowercase hex characters, full file>",
        "size_bytes": "<nonnegative JSON integer; placeholder here>",
        "media": {
          "duration_seconds": "<positive finite JSON number>",
          "width": "<positive JSON integer>",
          "height": "<positive JSON integer>",
          "fps": "<positive finite number, when available>"
        }
      },
      "source_location": {
        "recorded_path": "<historical locator; informational>"
      }
    }

Angle-bracket values are illustrative placeholders, not valid artifact values.
Other existing manifest fields retain their evidence and policy meanings.
There is no new Shared Analysis schema in this design: existing schema-1 analysis
bytes remain unchanged, including source_video.path and source_video.sha256.

## Authoritative fields and exact relocation gate

All of the following must pass; none may be inferred or silently repaired:

1. Supported manifest/identity versions, algorithm and well-formed fields.
   Reject booleans as numbers, nonfinite values, absent hashes and unknown versions.
2. An explicitly supplied readable source file; existing path/symlink/collision
   protections remain. The historical locator is never an instruction to fetch
   media or search other directories.
3. Full-file SHA-256 of the supplied source equals BOTH manifest identity.digest
   and analysis source_video.sha256. Required size_bytes equals actual bytes read;
   size is an additional consistency/fast-rejection check, not a digest substitute.
4. Source duration/dimensions/FPS match the manifest's non-location source
   metadata under existing comparison behavior. Analysis/source duration retains
   the current 1e-6 absolute tolerance. Do not relax metadata comparisons to
   accommodate another FFprobe build; reject discrepancies for separate review.
5. Shared-analysis schema and raw-file hash match the manifest exactly. A
   whitespace-only or locator-only edit invalidates that binding. No semantic
   JSON hash replacement is proposed.
6. Existing candidate evidence, ranking provenance, boundaries, encoding,
   successful statuses/counts, selection/plan checks and output hashes match.
   Output stream/duration validation and existing tolerances remain unchanged.
7. Reads observe a stable source/artifact set; detected disappearance or mutation
   fails. No concurrent writes are permitted operationally. There is no encoding,
   inference, repair, migration, directory creation or manifest rewrite in cache-only.

The runtime source path, filename, parent directory and filesystem mtime are
locators/observations, not content identity. Size/duration can agree for different
bytes; names can be reused; mtimes can be copied or changed. None alone, or in
combination without a trusted digest reference, proves byte equivalence.
Renamed source stems may still change output discovery: V2 identity acceptance
does not imply automatic artifact discovery or arbitrary path scanning.

Only source location is removed from equality. Preserve existing historical
selection provenance and its plan binding; do not normalize every path recursively.
Long-form signature serialization must have an explicit V2 domain/version and
deterministic JSON definition, without runtime locators. Existing V1 signatures
remain untouched and are interpreted only by their V1 reader.

## Compatibility and failure rules

| Input | Proposed future behavior |
|---|---|
| Legacy manifest version 1 | Existing strict reader and path binding, unchanged; no automatic upgrade |
| Version 2 / identity version 1 | Apply the full gate above; only locator differences may be accepted |
| Missing/unknown version, malformed identity | Reject; never guess a legacy/new format |
| Missing source | Reject even if all rendered outputs exist |
| Changed bytes, including same name/size/duration | Reject source identity mismatch |
| Mismatched analysis, corrupt output or failed records | Reject without repairing or adopting the cache |
| Legacy source digest absent/conflicting | Reject portable reuse/migration; hashing today's file cannot establish historical identity |
| Pair of V1 and V2 manifests | No implicit conversion; future migration activation must publish a coherent pair |

A compatibility reader cannot silently reinterpret V1 as V2. Opt-in migration
creates new artifacts on copies; legacy export behavior remains available.
Current code rejects version 2: skipped tests are specifications, not support claims.

## Migration integrity and recovery

Migration must first validate all content/evidence, then stage a complete new
generation with both manifests, a migration record and verified output references
or copies. The record must retain old manifest hashes/versions, original locations,
analysis hash, source digest, and new hashes plus tool/contract version.
Keep original analysis/MP4s/research reports byte-identical.

Two independent file replacements are NOT a transaction. A later implementation
must activate a staged generation through one atomic same-filesystem publication
boundary (for example an immutable bundle plus one activation record understood by
the future reader). Revalidate inputs before publication; fsync/rename guarantees
and Windows open-handle behavior require platform tests. Never activate half a
pair. Failure before activation leaves V1 authoritative; staged state is inspectable,
not auto-adopted. Rollback switches to the intact prior generation; no destructive
in-place reverse rewrite or automatic deletion of evidence.

## Performance, security and limitations

Hash in bounded chunks; full hashing is O(file size) I/O and can be expensive.
Reuse one validated digest within a stable explicit operation only after designing
race safeguards; do not add a persistent size/mtime-only digest cache or sampled
hash shortcut. This milestone adds no production execution or hashing path.
Required V2 size can be measured during the same read as a later migration digest.

Hashes provide integrity relative to a trustworthy record, not authentication:
an attacker able to replace both media and manifests can replace their digests.
SHA-256 is practical cryptographic evidence, not a mathematical collision-proof
guarantee or signed provenance. Path traversal, symlinks, concurrent mutation,
network/OneDrive semantics and hash/probe time-of-check gaps still require care.
Probe metadata can differ across tools; conservatively reject rather than assume
equivalence. No new lock or transaction implementation is claimed.

Open implementation decisions: exact V2 signature serialization, activation bundle
layout/reader selection, stable-read safeguards and Windows durability guarantees,
and discovery of renamed sources. Until resolved, use the conservative V1 policy.
