# Source identity migration plan

Implementation status (2026-10-22): explicit V2 readers and isolated fresh V2
writers now exist in both exporters. Shared Analysis remains schema 1. No
migration utility, pair activation or rollback transaction is implemented.
Preserve existing production exports and research. Steps 1-3 below are the
original rollout plan; canonical signatures and the three supported deferred
contract cases are now implemented. Step 4 onward remains future work.

1. Freeze the contract in portable_source_identity_v1.md and review unresolved
   signature, activation and stable-read decisions before coding. Maintain
   Shared Analysis schema 1; propose export manifest 2 / source_identity 1.
2. Implement a read-only version-dispatch reader in a later milestone. Keep the
   V1 reader/error behavior intact. V2 compares full digest, size and non-location
   media metadata, raw analysis hash, and unchanged plan/output integrity.
   Unknown versions/missing identity fail closed. Cache-only never migrates.
3. Enable deferred tests only against that implementation. Use tiny synthetic
   fixtures and mocked probes with real file hashing. Cover same bytes/new path,
   same name/size/duration/different bytes, missing/conflicting digests, unsupported
   versions, source mutation, changed analysis, corrupt outputs, path traversal,
   symlinks and no writes. Retain all current V1 relocation rejection tests.
4. Design opt-in dry-run migration separately. Require an explicit candidate
   source and complete old artifacts. Check matching recorded source digests in
   analysis and both legacy manifests, unchanged analysis/output hashes, plans
   and technical metadata. V1 relocation rejection is not bypassed in export:
   the migration validator explicitly diagnoses location-only mismatch. Any
   missing trustworthy historical digest or other mismatch blocks migration.
5. Stage new versioned manifests/transaction record in a new generation on copies.
   Do not rewrite original analysis locators, MP4s, model provenance, ground truth
   or frozen reports. Add size from verified reads, retain legacy manifest hashes
   and historical paths, and preserve original selection/encoding semantics.
6. Test failure injection around staging, validation, crash and activation on
   Windows. Publish the complete pair through a single atomic activation boundary;
   do not describe two manifest renames as atomic. Recheck all inputs immediately
   before activation. Unknown/incomplete staging is never an eligible cache.
7. Roll out first on fixtures, then an explicitly authorized copied production
   bundle and a second Windows machine. Run full verification and read-only V2
   cache checks, comparing all original hashes/mtimes. No inference or encoding.
   Record tool versions and migration evidence; do not tune tolerances on failures.
8. Roll back by selecting the untouched previous generation. Existing binaries
   cannot read V2: retain an explicit way to select V1 rather than overwriting it.
   Staged or failed bundles remain inactive; cleanup requires a separate action.

Remaining unresolved: bundle/activation naming and discovery, filesystem
transaction durability, stable source hashing/probing under concurrent access,
and renamed-stem lookup. Canonical signature rules and best-effort stable-read
checks are documented in portable_source_identity_v1.md. New V2 creation is
restricted to isolated empty destinations; it does not convert existing artifacts.
Default to rejecting ambiguity. Model environments and dependency consolidation
are independent milestones. No success criterion requires relaxing legacy safety.
