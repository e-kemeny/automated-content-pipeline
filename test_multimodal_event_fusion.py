"""Synthetic saved-data fusion tests; no OCR engines, models or media processing."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import multimodal_event_fusion as fusion
from shared_analysis import create_analysis, signal
from multimodal_timeline import build_timeline
from transcript_event_recognition import recognize_events
from ocr_evidence_interpretation import interpret_evidence
from ocr_visual_evidence import recognize_bundle
from test_ocr_visual_evidence import bundle, FakeBackend


class FusionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        manifest, _ = bundle(self.root, crops=False)
        self.raw = recognize_bundle(manifest, backend=FakeBackend(dict(text="VICTORY", words=[
            dict(text="VICTORY", confidence=91)])))
        self.ocr = interpret_evidence(self.raw)
        analysis = create_analysis(dict(path="fixture.mp4", sha256="a"*64, size_bytes=123,
                                        duration_seconds=10, width=160, height=100))
        analysis["transcript"] = signal([dict(start=0, end=2, text="We won the game.")], dict(backend="fixture"))
        analysis["acoustic"]["audio_activity"] = signal([dict(second=.5, score=3)])
        self.timeline = build_timeline(analysis=analysis)
        self.transcript = recognize_events(self.timeline)

    def fused(self, **kwargs):
        args = dict(transcript=self.transcript, ocr=self.ocr, timeline=self.timeline,
                    ocr_time_offset_seconds=0, alignment_reference="synthetic clocks share zero")
        args.update(kwargs)
        return fusion.fuse_events(**args)

    def test_matching_hypotheses_and_context(self):
        result = self.fused()
        self.assertEqual(len(result["groups"]), 1)
        group = result["groups"][0]
        self.assertEqual(group["event_type"], "victory")
        self.assertEqual(group["evidence_count"], 2)
        self.assertEqual(group["source_agreement"], "cross_modality_label_overlap")
        self.assertIsNone(group["gameplay_event_interval"])
        self.assertEqual(group["observation_envelope"], dict(start_seconds=0, end_seconds=2))
        self.assertEqual(len(group["context_references"]), 2)
        self.assertTrue(all(c["role"] == "temporal_context_only" for c in result["context_observations"]))

    def test_unverified_clocks_do_not_fuse(self):
        result = self.fused(ocr_time_offset_seconds=None, alignment_reference=None)
        self.assertEqual(len(result["groups"]), 2)
        self.assertTrue(all(g["evidence_count"] == 1 for g in result["groups"]))

    def test_nonmatching_semantics(self):
        raw = deepcopy(self.raw)
        raw["observations"][0]["text"] = "you died"
        self.ocr = interpret_evidence(raw)
        self.assertEqual(len(self.fused()["groups"]), 2)

    def test_nonoverlap_and_shared_endpoint(self):
        for offset in (1.5, 3):
            with self.subTest(offset=offset):
                self.assertEqual(len(self.fused(ocr_time_offset_seconds=offset)["groups"]), 2)

    def test_overlap_utilities_and_no_chain_bridge(self):
        self.assertTrue(fusion.overlaps((1, 3), (2, 4)))
        self.assertTrue(fusion.overlaps((2, 2), (2, 2)))
        self.assertFalse(fusion.overlaps((1, 2), (2, 3)))
        analysis = create_analysis(dict(path="fixture.mp4", sha256="a"*64, duration_seconds=10))
        analysis["transcript"] = signal([dict(start=s, end=e, text="We won the game.")
                                        for s, e in ((0, 2), (1, 3), (2.5, 4))])
        result = fusion.fuse_events(transcript=recognize_events(build_timeline(analysis=analysis)))
        self.assertEqual(sorted(g["evidence_count"] for g in result["groups"]), [1, 2])

    def test_missing_timestamp_rejected(self):
        del self.transcript["hypotheses"][0]["original_observation"]["start_seconds"]
        with self.assertRaises(ValueError):
            self.fused()

    def test_missing_modalities_and_empty_inputs(self):
        result = fusion.fuse_events(transcript=self.transcript)
        self.assertEqual(result["modalities"]["ocr"]["status"], "missing")
        self.assertEqual(result["modalities"]["timeline"]["temporal_coverage"], "unknown")
        self.assertEqual(fusion.fuse_events()["groups"], [])
        result = fusion.fuse_events(ocr=interpret_evidence(None))
        self.assertEqual(result["inputs"]["ocr"]["status"], "not_analyzed")
        self.assertEqual(result["groups"], [])

    def test_identity_conflict(self):
        self.raw["source_identity"]["digest"] = "b"*64
        self.raw["visual_evidence_provenance"]["manifest"]["source_identity"]["digest"] = "b"*64
        self.ocr = interpret_evidence(self.raw)
        with self.assertRaisesRegex(ValueError, "identity mismatch"):
            self.fused()

    def test_missing_identity_cannot_merge(self):
        analysis = create_analysis(dict(path="fixture.mp4", duration_seconds=10))
        analysis["transcript"] = signal([dict(start=0, end=2, text="We won the game.")])
        self.transcript = recognize_events(build_timeline(analysis=analysis))
        with self.assertRaises(ValueError):
            self.fused(timeline=None)

    def test_duplicate_hypothesis_counted_once(self):
        self.transcript["hypotheses"].append(deepcopy(self.transcript["hypotheses"][0]))
        result = self.fused()
        self.assertEqual(result["groups"][0]["evidence_count"], 2)
        self.assertEqual(len(result["duplicate_references"]), 1)
        self.assertEqual(len(result["inputs"]["transcript"]["hypotheses"]), 2)

    def test_conflicting_duplicate_rejected(self):
        duplicate = deepcopy(self.transcript["hypotheses"][0])
        duplicate["event_type"] = "death"
        self.transcript["hypotheses"].append(duplicate)
        with self.assertRaises(ValueError):
            self.fused()

    def test_ocr_interpretation_tampering(self):
        self.ocr["interpretations"][0]["hypotheses"][0]["event_type"] = "kill"
        with self.assertRaises(ValueError):
            self.fused()

    def test_provenance_and_schema_rejected(self):
        for key, value in (("schema_version", True), ("schema_version", 2),
                           ("artifact_type", "wrong"), ("source_identity_status", "verified")):
            data = deepcopy(self.transcript)
            data[key] = value
            with self.subTest(key=key, value=value), self.assertRaises(ValueError):
                self.fused(transcript=data)
        self.transcript["input_provenance"]["timeline_sha256"] = "b"*64
        with self.assertRaises(ValueError):
            self.fused()

    def test_ocr_embedded_source_conflict(self):
        self.raw["visual_evidence_provenance"]["manifest"]["source_identity"]["digest"] = "b"*64
        self.ocr = interpret_evidence(self.raw)
        with self.assertRaises(ValueError):
            self.fused()

    def test_ocr_frame_provenance_mismatch(self):
        self.raw["observations"][0]["timestamp"] = dict(normalized_pts=7, time_base="1/10", timestamp_seconds=.7)
        self.ocr = interpret_evidence(self.raw)
        with self.assertRaises(ValueError):
            self.fused()

    def test_detector_provenance_mismatch(self):
        self.transcript["detector"]["guards"] = []
        with self.assertRaises(ValueError):
            self.fused()

    def test_distinct_ocr_points_do_not_claim_shared_event(self):
        first = deepcopy(self.raw["observations"][0])
        second = deepcopy(first)
        second.update(observation_id="second", parent_frame_id="frame-two")
        second["timestamp"] = dict(normalized_pts=15, time_base="1/10", timestamp_seconds=1.5)
        frame = deepcopy(self.raw["visual_evidence_provenance"]["manifest"]["frames"][0])
        frame.update(frame_id="frame-two", **second["timestamp"])
        second["image"] = {k: v for k, v in frame.items() if k != "regions"}
        self.raw["observations"].append(second)
        self.raw["visual_evidence_provenance"]["manifest"]["frames"].append(frame)
        self.ocr = interpret_evidence(self.raw)
        result = self.fused()
        self.assertEqual(sorted(g["evidence_count"] for g in result["groups"]), [1, 2])

    def test_unknown_game_fallback_retained(self):
        self.ocr = interpret_evidence(self.raw, game="unrecognized")
        result = self.fused()
        self.assertTrue(result["inputs"]["ocr"]["unknown_game_fallback"])
        self.assertEqual(len(result["groups"]), 1)

    def test_preservation_determinism_and_no_subprocess(self):
        before = deepcopy((self.transcript, self.ocr, self.timeline))
        with patch("subprocess.run", side_effect=AssertionError("No inference or media allowed")):
            first, second = self.fused(), self.fused()
        self.assertEqual(first, second)
        self.assertEqual(before, (self.transcript, self.ocr, self.timeline))
        self.assertEqual(first["inputs"]["ocr"], self.ocr)
        member = next(m for m in first["groups"][0]["members"] if m["modality"] == "ocr")
        self.assertEqual(member["original_evidence"]["observation"]["words"][0]["confidence"], 91)

    def test_invalid_alignment(self):
        for args in (dict(ocr_time_offset_seconds=float("nan")), dict(ocr_time_offset_seconds=-1),
                     dict(alignment_reference=""), dict(alignment_reference=None)):
            with self.subTest(args=args), self.assertRaises(ValueError):
                self.fused(**args)

    def test_failed_ocr_is_not_negative(self):
        raw = deepcopy(self.raw)
        raw["observations"][0].update(status="failed", text=None, words=None, error="fixture")
        self.ocr = interpret_evidence(raw)
        result = self.fused()
        self.assertEqual(result["groups"][0]["source_agreement"], "single_modality")
        self.assertEqual(result["inputs"]["ocr"]["interpretations"][0]["status"], "ocr_failed")

    def test_atomic_failure_and_safe_publication(self):
        source, output = self.root/"ocr.json", self.root/"fusion.json"
        source.write_text(json.dumps(self.ocr), encoding="utf-8")
        before = source.read_bytes(), source.stat().st_mtime_ns
        args = ["--ocr", str(source), "--output", str(output)]
        with contextlib.redirect_stderr(io.StringIO()), contextlib.redirect_stdout(io.StringIO()):
            with patch("timeline_query.os.link", side_effect=OSError("simulated publication failure")):
                self.assertEqual(fusion.main(args), 1)
            self.assertFalse(output.exists())
            self.assertEqual(list(self.root.glob(".query-*")), [])
            self.assertEqual(fusion.main(args), 0)
            saved = output.read_bytes(), output.stat().st_mtime_ns
            self.assertEqual(fusion.main(args), 1)
            self.assertEqual(saved, (output.read_bytes(), output.stat().st_mtime_ns))
            self.assertEqual(fusion.main(["--ocr", str(source), "--output", str(source)]), 1)
        self.assertEqual(before, (source.read_bytes(), source.stat().st_mtime_ns))
        self.assertEqual(json.loads(saved[0]), fusion.fuse_events(ocr=self.ocr))


if __name__ == "__main__":
    unittest.main()
