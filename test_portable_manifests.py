"""V2 exporter fixtures use real source hashing/planning and mocked encoding/probes."""
import contextlib
import io
import json
from pathlib import Path
import unittest
from unittest.mock import patch

import export_shorts as shorts
import export_longform as longform
import pipeline
import source_identity as identity
import test_artifact_relocation as relocation
from verify import snapshot


class PortableFixture:
    def __init__(self, case):
        self.case = case
        self.root, self.video, self.analysis = case.root, case.video, case.analysis
        self.output = self.root/"v2"
        self.durations = {}
        self.encodes = []
        self.create()

    def probe(self, path):
        path = Path(path)
        duration = self.durations.get(path, 110 if path.name == "longform_v1.mp4" else 15)
        return dict(duration_seconds=duration, streams=[
            dict(codec_type="audio"), dict(codec_type="video",avg_frame_rate="30/1")])

    def encode(self, command, **kwargs):
        self.encodes.append(command)
        path = Path(command[-1])
        if "-t" in command:
            duration = float(command[command.index("-t")+1])
        else:
            listing = Path(command[command.index("-i")+1])
            duration = sum(self.durations[listing.parent/line.split("'")[1]]
                           for line in listing.read_text().splitlines())
        self.durations[path] = duration
        path.write_bytes(("synthetic encoded "+str(duration)).encode())

    def create(self):
        with (
            patch("subprocess.run",side_effect=self.encode),
            patch.object(shorts,"probe_clip",side_effect=self.probe),
            patch.object(longform,"probe_clip",side_effect=self.probe),
        ):
            for exporter in (shorts.export_shorts,longform.export_longform):
                exporter(self.video,self.analysis,output_root=self.output,manifest_version=2)

    def files(self):
        return [p for p in self.root.rglob("*") if p.is_file()]

    @contextlib.contextmanager
    def read_only(self):
        before = snapshot(self.files())
        try:
            with (
                patch("subprocess.run",side_effect=AssertionError("No encoding")),
                patch.object(shorts,"probe_clip",side_effect=self.probe),
                patch.object(longform,"probe_clip",side_effect=self.probe),
                patch.object(Path,"mkdir",side_effect=AssertionError("No mkdir")),
                patch("tempfile.NamedTemporaryFile",side_effect=AssertionError("No write")),
                patch("tempfile.TemporaryDirectory",side_effect=AssertionError("No workdir")),
                patch("os.replace",side_effect=AssertionError("No replace")),
            ):
                yield
        finally:
            assert before == snapshot(self.files()), "Artifact changed during cache-only"

    def relocate(self):
        destination = self.root/"relocated"
        destination.mkdir()
        self.video = self.video.rename(destination/self.video.name)

    def manifests(self):
        return sorted(self.output.rglob("*manifest.json"))

    def check(self):
        with self.read_only():
            results = [exporter(self.video,self.analysis,output_root=self.output,
                                manifest_version=2,cache_only=True)
                       for exporter in (shorts.export_shorts,longform.export_longform)]
        return results


@contextlib.contextmanager
def fixture():
    case = relocation.RelocationTests()
    case.setUp()
    try:
        yield PortableFixture(case)
    finally:
        case.doCleanups()


class PortableManifestTests(unittest.TestCase):
    def test_v2_creation_and_relocation_pipeline(self):
        with fixture() as f:
            self.assertEqual(len(f.encodes), 7)  # Five clips, one merged intermediate, concat.
            f.relocate()
            f.check()
            with f.read_only(), contextlib.redirect_stdout(io.StringIO()) as out:
                code = pipeline.main([str(f.video),"--analysis",str(f.analysis),"--mode","both",
                    "--manifest-version","2","--output-root",str(f.output),"--cache-only"])
            self.assertEqual(code,0)
            self.assertIn("Shorts: success",out.getvalue())
            self.assertIn("Long-form: success",out.getvalue())

    def test_changed_source_same_size_and_missing(self):
        for mode in ("changed","missing"):
            with self.subTest(mode=mode), fixture() as f:
                if mode == "changed": f.video.write_bytes(b"x"*f.video.stat().st_size)
                else: f.video.unlink()
                with f.read_only():
                    for exporter in (shorts.export_shorts,longform.export_longform):
                        with self.assertRaisesRegex((ValueError,OSError),"Source identity mismatch|Media file not found"):
                            exporter(f.video,f.analysis,output_root=f.output,manifest_version=2,cache_only=True)

    def test_tampered_manifests_fail_closed(self):
        for field in ("digest","size","identity_version","algorithm","media","analysis",
                      "encoding","signature","boundary","output_hash","status"):
            with self.subTest(field=field), fixture() as f:
                for path in f.manifests():
                    m = json.loads(path.read_text())
                    if field == "digest": m["source_identity"].pop("digest")
                    elif field == "size": m["source_identity"]["size_bytes"] += 1
                    elif field == "identity_version": m["source_identity"]["version"] = 2
                    elif field == "algorithm": m["source_identity"]["algorithm"] = "md5"
                    elif field == "media": m["source_identity"]["media"]["width"] = True
                    elif field == "analysis": m["shared_analysis"]["sha256"] = "0"*64
                    elif field == "encoding": m["encoding"]["crf"] = 99
                    elif field == "signature": m["plan_signature"] = "0"*64
                    elif field == "boundary":
                        if "clips" in m: m["clips"][0]["start"] += 1
                        else: m["planning"]["source_intervals"][0]["start"] += 1
                    elif field == "output_hash":
                        if "clips" in m: m["clips"][0]["output_sha256"] = "0"*64
                        else: m["assembly"]["output_sha256"] = "0"*64
                    elif field == "status":
                        if "clips" in m: m["clips"][0]["status"] = "failed"
                        else: m["assembly"]["status"] = "failed"
                    path.write_text(json.dumps(m))
                with f.read_only():
                    for exporter in (shorts.export_shorts,longform.export_longform):
                        with self.assertRaises(ValueError):
                            exporter(f.video,f.analysis,output_root=f.output,manifest_version=2,cache_only=True)

    def test_corrupt_output_and_analysis_bytes(self):
        for kind in ("output","analysis"):
            with self.subTest(kind=kind), fixture() as f:
                if kind == "analysis": f.analysis.write_bytes(f.analysis.read_bytes()+b" ")
                else:
                    for path in f.output.rglob("*.mp4"): path.write_bytes(b"corrupt")
                with f.read_only():
                    for exporter in (shorts.export_shorts,longform.export_longform):
                        with self.assertRaisesRegex(ValueError,"stale shared analysis|Cache-only hash mismatch"):
                            exporter(f.video,f.analysis,output_root=f.output,manifest_version=2,cache_only=True)

    def test_no_implicit_conversion_or_existing_destination_replace(self):
        with fixture() as f:
            with f.read_only():
                for exporter in (shorts.export_shorts,longform.export_longform):
                    for root, version, kwargs in (
                        (f.case.output,2,{"cache_only":True}), (f.output,1,{"cache_only":True}),
                        (f.case.output,2,{}), (f.output,2,{}), (f.output,2,{"force":True}),
                    ):
                        with self.assertRaises(ValueError):
                            exporter(f.video,f.analysis,output_root=root,manifest_version=version,**kwargs)
            f.case.check_both()  # Legacy V1 still valid and unchanged at original location.

    def test_isolated_destination_required_and_dry_run_no_writes(self):
        with fixture() as f:
            with f.read_only():
                for exporter in (shorts.export_shorts,longform.export_longform):
                    with self.assertRaisesRegex(ValueError,"isolated"):
                        exporter(f.video,f.analysis,manifest_version=2,dry_run=True)
                    _, m = exporter(f.video,f.analysis,output_root=f.root/"new",
                                    manifest_version=2,dry_run=True)
                    self.assertEqual(m["manifest_version"],2)
                self.assertFalse((f.root/"new").exists())

    def test_missing_output_and_partial_pipeline(self):
        with fixture() as f:
            next((f.output/"game"/"shorts").glob("*.mp4")).unlink()
            with f.read_only(), contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
                code = pipeline.main([str(f.video),"--analysis",str(f.analysis),
                    "--manifest-version","2","--output-root",str(f.output),"--cache-only"])
            self.assertEqual(code,1)
            self.assertIn("partial failure",out.getvalue())

    def test_signature_determinism_and_locator_exclusion(self):
        with fixture() as f:
            for path in f.manifests():
                m = json.loads(path.read_text())
                signature = identity.plan_signature(m)
                self.assertEqual(signature,m["plan_signature"])
                m["source"]["path"] = "another"
                m["source_location"]["recorded_path"] = "elsewhere"
                m["shared_analysis"]["path"] = "new-analysis-locator"
                if "assembly" in m: m["assembly"]["output_path"] = "new-output"
                self.assertEqual(signature,identity.plan_signature(m))
            self.assertEqual(identity.canonical({"z":1,"a":chr(233)}), b'{"a":"\\u00e9","z":1}')

    def test_atomic_exclusive_publication_failure_never_valid_cache(self):
        with fixture() as f:
            destination = f.root/"failed"
            real_link = shorts.os.link
            def fail_manifest(source,target):
                if str(target).endswith(".json"):
                    raise OSError("fixture publication failure")
                return real_link(source,target)
            with (
                patch("subprocess.run",side_effect=f.encode),
                patch.object(shorts,"probe_clip",side_effect=f.probe),
                patch.object(longform,"probe_clip",side_effect=f.probe),
                patch("os.link",side_effect=fail_manifest),
            ):
                for exporter in (shorts.export_shorts,longform.export_longform):
                    with self.assertRaisesRegex(OSError,"publication failure"):
                        exporter(f.video,f.analysis,output_root=destination,manifest_version=2)
            with f.read_only():
                for exporter in (shorts.export_shorts,longform.export_longform):
                    with self.assertRaises(OSError):
                        exporter(f.video,f.analysis,output_root=destination,manifest_version=2,cache_only=True)


if __name__ == "__main__":
    unittest.main()
