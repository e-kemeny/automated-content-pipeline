"""Current identity guarantees; future portable-manifest behavior is explicitly skipped."""
import contextlib
import json
import shutil
import unittest
import test_artifact_relocation as relocation
import export_shorts as shorts


class SourceIdentityContractTests(unittest.TestCase):
    @contextlib.contextmanager
    def fixture(self):
        case = relocation.RelocationTests()
        case.setUp()
        try:
            yield case
        finally:
            case.doCleanups()

    def test_legacy_same_path_unchanged_content(self):
        with self.fixture() as case:
            for path in case.manifests:
                self.assertEqual(json.loads(path.read_text())["manifest_version"], 1)
            case.check_both()

    def test_identical_content_relocated_is_rejected_by_legacy(self):
        with self.fixture() as case:
            folder = case.root/"new_location"
            folder.mkdir()
            moved = folder/case.video.name
            shutil.copy2(case.video, moved)
            self.assertEqual(shorts.media_sha256(case.video), shorts.media_sha256(moved))
            case.check_both(video=moved, error="Cache-only stale manifest: source")

    def test_same_filename_same_size_duration_different_bytes(self):
        with self.fixture() as case:
            folder = case.root/"other"
            folder.mkdir()
            other = folder/case.video.name
            other.write_bytes(b"x"*case.video.stat().st_size)
            self.assertEqual(other.name, case.video.name)
            self.assertEqual(other.stat().st_size, case.video.stat().st_size)
            # Fixture probes both as 120 seconds; real source hashing still runs.
            self.assertNotEqual(shorts.media_sha256(other), shorts.media_sha256(case.video))
            case.check_both(video=other, error="Source identity mismatch")

    def test_changed_bytes_original_path(self):
        with self.fixture() as case:
            case.video.write_bytes(b"x"*case.video.stat().st_size)
            case.check_both(error="Source identity mismatch")

    def test_missing_source(self):
        with self.fixture() as case:
            case.video.unlink()
            case.check_both(error="Media file not found:")

    def test_legacy_without_analysis_digest_cannot_establish_identity(self):
        with self.fixture() as case:
            data = json.loads(case.analysis.read_text())
            del data["source_video"]["sha256"]
            case.analysis.write_text(json.dumps(data))
            case.check_both(error="Persisted SHA-256 source identity required")

    def test_changed_analysis_and_corrupt_cache_rejected_read_only(self):
        for corruption in ("analysis", "clip"):
            with self.subTest(corruption=corruption), self.fixture() as case:
                if corruption == "analysis":
                    case.analysis.write_bytes(case.analysis.read_bytes()+b" ")
                    error = "Cache-only stale shared analysis"
                else:
                    for path in case.output.rglob("*.mp4"):
                        path.write_bytes(b"corrupt")
                    error = "Cache-only hash mismatch:"
                # Actual validators, no writes/encoding, byte/hash/mtime snapshots.
                case.check_both(error=error)

    def test_unknown_manifest_version_rejected(self):
        with self.fixture() as case:
            for path in case.manifests:
                data = json.loads(path.read_text())
                data["manifest_version"] = 2
                path.write_text(json.dumps(data))
            case.check_both(error="Cache-only stale manifest: manifest_version|Existing manifest is unrelated or invalid; refusing replacement")


@unittest.skip("DESIGN ONLY: manifest v2/source_identity v1 reader and migration are not implemented")
class FuturePortableIdentityContractTests(unittest.TestCase):
    def test_v2_same_digest_size_and_metadata_allows_new_locator(self):
        """Permit relocation only after all criteria in the design pass."""
        self.fail("Implement against the future production V2 reader before enabling")

    def test_v2_missing_digest_never_falls_back_to_name_size_or_time(self):
        """Unknown identity fails closed; no on-the-fly upgrade."""
        self.fail("Implement against the future production V2 reader before enabling")

    def test_v2_cache_only_never_writes_or_migrates(self):
        """V2 readers must retain the existing strict no-write guarantee."""
        self.fail("Implement against the future production V2 reader before enabling")

    def test_migration_bundle_failure_preserves_v1_and_no_partial_activation(self):
        """Publication must not leave a mixed pair of active manifests."""
        self.fail("Implement against the future migration transaction before enabling")


if __name__ == "__main__":
    unittest.main()
