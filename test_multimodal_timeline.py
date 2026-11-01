"""Synthetic fixtures follow existing saved schemas; no media or model required."""
from copy import deepcopy
import contextlib
import importlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from shared_analysis import create_analysis, signal
import multimodal_timeline as timeline

HASH = "a"*64


def analysis():
    result = create_analysis(dict(path="fixture.mp4", duration_seconds=10, sha256=HASH))
    result["acoustic"]["audio_activity"] = signal([
        dict(second=3, spike=-2, score=4, normalized_score=.25)], dict(detector="existing"))
    result["visual"]["scene_changes"] = signal([dict(time=3, score=12)])
    result["transcript"] = signal([dict(start=1.25, end=4.5, text=" Original text. ",
        metadata=dict(words=[dict(start=1.25, end=2, word=" Original", probability=.8)]))],
        dict(source_sha256=HASH, source_duration_seconds=10, model="small.en"))
    return result


def transcript():
    return dict(segments=[dict(start=2, end=5, text="Fixture")],
                provenance=dict(source_sha256=HASH, source_duration_seconds=10, model="small.en"))


def vision():
    return dict(schema_version=1, experiment="vision-inference-v1",
        video=dict(path="elsewhere/fixture.mp4", sha256=HASH, size_bytes=123,
                   duration_seconds=10, width=160, height=90, stream_index=0),
        model=dict(name="resnet18", weights="ResNet18_Weights.IMAGENET1K_V1",
                   weights_url="fixture-url"),
        sampling=dict(method="duration*i/(count+1), i=1..count", frame_count=1),
        runtime=dict(device="cuda:0", gpu_name="fixture GPU", pytorch_version="fixture",
                     torchvision_version="fixture", cuda_build_version="fixture",
                     total_elapsed_seconds=1, peak_allocated_gpu_memory_mib=20),
        frames=[dict(timestamp_seconds=5, inference_latency_ms=1.2, top3=[
            dict(category="tench", confidence=.6), dict(category="goldfish", confidence=.3),
            dict(category="shark", confidence=.1)])])


class TimelineTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.output = self.root/"new"/"timeline.json"

    def test_audio_and_scene_adapters(self):
        a = analysis()
        result = timeline.build_timeline(analysis=a)
        audio = next(e for e in result["events"] if e["modality"] == "audio")
        scene = next(e for e in result["events"] if e["event_type"] == "scene_change")
        self.assertEqual(audio["event_type"], "audio_spike_score")
        self.assertEqual(audio["payload"], a["acoustic"]["audio_activity"]["data"][0])
        self.assertEqual(scene["payload"], a["visual"]["scene_changes"]["data"][0])
        self.assertEqual((audio["start_seconds"], audio["end_seconds"]), (3, 3))
        self.assertEqual(audio["observation_kind"], "point")

    def test_transcript_interval_payload(self):
        a = analysis()
        row = timeline.build_timeline(transcript=a)["events"][0]
        self.assertEqual(row["payload"], a["transcript"]["data"][0])
        self.assertEqual((row["start_seconds"], row["end_seconds"]), (1.25, 4.5))
        self.assertEqual(row["observation_kind"], "interval")

    def test_standalone_transcription_result(self):
        result = timeline.build_timeline(transcript=transcript())
        self.assertEqual(result["events"][0]["payload"]["text"], "Fixture")
        self.assertEqual(result["duration_seconds"], 10)
        self.assertIsNone(result["source_identity"])

    def test_vision_and_identity_contract(self):
        v = vision()
        result = timeline.build_timeline(vision=v)
        row = result["events"][0]
        self.assertEqual(row["payload"], v["frames"][0])
        self.assertEqual((row["start_seconds"], row["end_seconds"]), (5, 5))
        self.assertEqual(row["source"]["provenance"]["model"], v["model"])
        self.assertEqual(result["source_identity"], dict(version=1, algorithm="sha256",
            digest=HASH, size_bytes=123, media=dict(duration_seconds=10, width=160, height=90)))

    def test_stable_sort_and_no_deduplication(self):
        a = analysis()
        a["visual"]["scene_changes"] = signal([dict(time=3, score=20), dict(time=3, score=10)])
        result = timeline.build_timeline(analysis=a, transcript=transcript(), vision=vision())
        self.assertEqual(result["events"], sorted(result["events"], key=timeline.sort_key))
        scenes = [r for r in result["events"] if r["event_type"] == "scene_change"]
        self.assertEqual([r["payload"]["score"] for r in scenes], [20, 10])
        tied = [r["modality"] for r in result["events"] if r["start_seconds"] == 3]
        self.assertEqual(tied, ["audio", "visual", "visual"])

    def test_partial_combinations(self):
        for inputs in (dict(analysis=analysis()), dict(transcript=transcript()), dict(vision=vision()),
                       dict(analysis=analysis(), vision=vision()), dict(transcript=transcript(), vision=vision())):
            self.assertTrue(timeline.build_timeline(**inputs)["events"])

    def test_empty_inputs_and_valid_empty_artifact(self):
        with self.assertRaises(ValueError):
            timeline.build_timeline()
        with self.assertRaises(ValueError):
            timeline.build_timeline(analysis={})
        empty = create_analysis(dict(path="fixture", duration_seconds=10))
        result = timeline.build_timeline(analysis=empty)
        self.assertEqual(result["events"], [])
        self.assertEqual(result["sources"][0]["channels"]["audio_activity"]["status"], "not_analyzed")
        empty["transcript"] = signal([])
        self.assertEqual(timeline.build_timeline(analysis=empty)["sources"][0]["channels"]["transcript"]["status"], "analyzed")

    def test_invalid_json_and_duplicates(self):
        path = self.root/"input.json"
        for text in ("{", "NaN", '{"x":1,"x":2}', '{"x":Infinity}'):
            path.write_text(text)
            with self.assertRaises(ValueError):
                timeline.read_json(path)

    def test_missing_timestamps(self):
        for kind, value, target, key in (
            ("analysis", analysis(), ("acoustic", "audio_activity", "data"), "second"),
            ("analysis", analysis(), ("visual", "scene_changes", "data"), "time"),
            ("transcript", transcript(), ("segments",), "start"),
            ("vision", vision(), ("frames",), "timestamp_seconds")):
            rows = value
            for field in target:
                rows = rows[field]
            del rows[0][key]
            with self.subTest(kind=kind), self.assertRaises(ValueError):
                timeline.build_timeline(**{kind:value})

    def test_invalid_point_times(self):
        for value in (-1, float("nan"), float("inf"), True, "3", 11):
            v = vision()
            v["frames"].append(deepcopy(v["frames"][0]))
            v["frames"][0]["timestamp_seconds"] = value
            with self.subTest(value=value), self.assertRaises(ValueError):
                timeline.build_timeline(vision=v)

    def test_reversed_negative_and_out_of_range_intervals(self):
        for start, end in ((5, 2), (-1, 2), (1, 11), (float("nan"), 2)):
            t = transcript()
            t["segments"][0].update(start=start, end=end)
            with self.assertRaises(ValueError):
                timeline.build_timeline(transcript=t)

    def test_zero_length_transcript_remains_interval(self):
        t = transcript()
        t["segments"][0].update(start=10, end=10)
        row = timeline.build_timeline(transcript=t)["events"][0]
        self.assertEqual(row["observation_kind"], "interval")

    def test_mismatched_source_hash_or_metadata(self):
        for key, value in (("sha256", "b"*64), ("duration_seconds", 11)):
            v = vision()
            v["video"][key] = value
            with self.assertRaisesRegex(ValueError, "identity mismatch"):
                timeline.build_timeline(analysis=analysis(), vision=v)

    def test_provenance_mismatch_rejected(self):
        a = analysis()
        a["transcript"]["provenance"]["source_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            timeline.build_timeline(analysis=a)

    def test_missing_identity_single_only(self):
        a = analysis()
        del a["source_video"]["sha256"]
        a["transcript"]["provenance"] = {}
        result = timeline.build_timeline(analysis=a)
        self.assertEqual(result["identity_status"], "unverified_single_artifact")
        with self.assertRaisesRegex(ValueError, "every source SHA-256"):
            timeline.build_timeline(analysis=a, vision=vision())
        t = dict(segments=[dict(start=1, end=100, text="x")], provenance={})
        self.assertIsNone(timeline.build_timeline(transcript=t)["duration_seconds"])

    def test_preservation_and_no_input_mutation(self):
        a, v = analysis(), vision()
        before = deepcopy((a, v))
        result = timeline.build_timeline(analysis=a, vision=v)
        result["events"][0]["payload"]["text"] = "changed"
        self.assertEqual((a, v), before)

    def test_unsupported_versions_and_raw_research_rejected(self):
        a = analysis()
        a["schema_version"] = 2
        v = vision()
        v["schema_version"] = 2
        for inputs in (dict(analysis=a), dict(vision=v), dict(transcript=[]),
                       dict(vision=dict(rows=[dict(timestamp=1)]))):
            with self.assertRaises(ValueError):
                timeline.build_timeline(**inputs)

    def test_required_event_metadata_and_modality(self):
        result = timeline.build_timeline(vision=vision())
        for field, value in (("modality", "other"), ("event_type", ""),
                             ("source", {}), ("payload", []), ("observation_kind", "guess")):
            bad = deepcopy(result)
            bad["events"][0][field] = value
            with self.assertRaises(ValueError):
                timeline.validate_timeline(bad)

    def test_roundtrip_and_existing_output_protection(self):
        result = timeline.build_timeline(analysis=analysis())
        timeline.save_timeline(result, self.output)
        original = self.output.read_bytes()
        self.assertEqual(timeline.validate_timeline(timeline.read_json(self.output)), result)
        with self.assertRaises(FileExistsError):
            timeline.save_timeline(result, self.output)
        timeline.save_timeline(result, self.output, overwrite=True)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_atomic_failure_preserves_output(self):
        result = timeline.build_timeline(analysis=analysis())
        timeline.save_timeline(result, self.output)
        original = self.output.read_bytes()
        with patch.object(timeline.os, "replace", side_effect=OSError("publish failed")):
            with self.assertRaises(OSError):
                timeline.save_timeline(result, self.output, overwrite=True)
        self.assertEqual(self.output.read_bytes(), original)
        self.assertEqual(list(self.output.parent.iterdir()), [self.output])

    def test_no_partial_new_file_on_failure(self):
        with patch.object(timeline.os, "link", side_effect=OSError("publish failed")):
            with self.assertRaises(OSError):
                timeline.save_timeline(timeline.build_timeline(vision=vision()), self.output)
        self.assertFalse(self.output.exists())
        self.assertEqual(list(self.output.parent.iterdir()), [])

    def test_no_clobber_concurrent_creation(self):
        def race(src, dest):
            dest.write_text("other")
            raise FileExistsError("race")
        with patch.object(timeline.os, "link", side_effect=race):
            with self.assertRaises(FileExistsError):
                timeline.save_timeline(timeline.build_timeline(vision=vision()), self.output)
        self.assertEqual(self.output.read_text(), "other")

    def test_validation_before_output_creation(self):
        bad = timeline.build_timeline(vision=vision())
        bad["events"][0]["start_seconds"] = -1
        with self.assertRaises(ValueError):
            timeline.save_timeline(bad, self.output)
        self.assertFalse(self.output.parent.exists())

    def test_cli_no_input_and_success_and_input_protection(self):
        path = self.root/"analysis.json"
        path.write_text(json.dumps(analysis()))
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            timeline.main([])
        self.assertEqual(raised.exception.code, 2)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(timeline.main(["--analysis", str(path), "--output", str(self.output)]), 0)
            self.assertEqual(timeline.main(["--analysis", str(path), "--output", str(path), "--overwrite"]), 1)
        self.assertEqual(timeline.read_json(path), analysis())


    def test_conflicting_channel_claims_without_header_hash(self):
        a = analysis()
        del a["source_video"]["sha256"]
        a["acoustic"]["audio_activity"]["provenance"]["source_sha256"] = "b"*64
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            timeline.build_timeline(analysis=a)

    def test_complete_identity_metadata_conflict(self):
        a = analysis()
        a["source_video"].update(width=320, height=90)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            timeline.build_timeline(analysis=a, vision=vision())

    def test_unrelated_output_not_overwritten(self):
        self.output.parent.mkdir()
        self.output.write_text('{"schema_version":1}')
        with self.assertRaises(ValueError):
            timeline.save_timeline(timeline.build_timeline(analysis=analysis()), self.output, overwrite=True)
        self.assertEqual(self.output.read_text(), '{"schema_version":1}')

    def test_no_heavy_imports_media_or_inference(self):
        import builtins
        original = builtins.__import__
        def guard(name, *args, **kwargs):
            if name.split(".")[0] in ("torch", "torchvision", "transformers", "faster_whisper", "PIL"):
                raise AssertionError("Heavy import")
            return original(name, *args, **kwargs)
        with (patch.object(builtins, "__import__", side_effect=guard),
              patch("subprocess.run", side_effect=AssertionError("External process")),
              patch("transcription.load_model", side_effect=AssertionError("Inference"))):
            importlib.reload(timeline)
            self.assertTrue(timeline.build_timeline(analysis=analysis(), vision=vision())["events"])


if __name__ == "__main__":
    unittest.main()
