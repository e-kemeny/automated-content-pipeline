"""Saved synthetic OCR fixtures only; never require an OCR installation."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

import ocr_evidence_interpretation as interpretation
from ocr_visual_evidence import recognize_bundle
from test_ocr_visual_evidence import bundle, FakeBackend


class InterpretationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        manifest, _ = bundle(self.root)
        self.evidence = recognize_bundle(manifest, backend=FakeBackend(
            dict(text="VICTORY", words=[dict(text="VICTORY", confidence=89.5)])))

    def run_interpretation(self, **kwargs):
        return interpretation.interpret_evidence(self.evidence, **kwargs)

    def test_generic_hypothesis(self):
        result = self.run_interpretation()
        match = result["interpretations"][0]["hypotheses"][0]
        self.assertEqual(match, dict(status="hypothesis", pattern_id="victory",
                                    event_type="victory", matched_text="VICTORY", text_span=[0, 7]))
        self.assertNotIn("confidence", match)

    def test_preserves_all_evidence_without_mutation(self):
        before = deepcopy(self.evidence)
        result = self.run_interpretation()
        self.assertEqual(result["input_evidence"], before)
        self.assertEqual(self.evidence, before)
        self.assertEqual(result["input_evidence"]["observations"][1]["kind"], "crop")
        self.assertEqual(result["input_evidence"]["observations"][1]["words"][0]["confidence"], 89.5)
        result["input_evidence"]["backend"]["version"] = "changed"
        self.assertEqual(self.evidence, before)

    def test_optional_bedwars_profile(self):
        for row in self.evidence["observations"]:
            row["text"] = "BED\nDESTROYED! Final kill"
        self.assertEqual(self.run_interpretation()["interpretations"][0]["status"], "no_match")
        result = self.run_interpretation(game="bedwars")
        matches = result["interpretations"][0]["hypotheses"]
        self.assertEqual([m["pattern_id"] for m in matches], ["bed_destroyed", "final_kill"])
        self.assertEqual(matches[0]["matched_text"], "BED\nDESTROYED")

    def test_unknown_game_falls_back_explicitly(self):
        result = self.run_interpretation(game="unrecognized-game")
        self.assertTrue(result["unknown_game_fallback"])
        self.assertEqual(result["requested_game"], "unrecognized-game")
        self.assertEqual(result["profile"]["name"], "generic")

    def test_custom_literal_not_regex_and_whole_phrase(self):
        for row in self.evidence["observations"]:
            row["text"] = "xvictory victoryx A+B a+b"
        profile = dict(schema_version=1, name="custom", patterns=[
            dict(id="literal", event_type="custom", phrase="a+b")])
        matches = self.run_interpretation(profile=profile)["interpretations"][0]["hypotheses"]
        self.assertEqual([m["matched_text"] for m in matches], ["A+B", "a+b"])
        self.assertEqual(self.run_interpretation()["interpretations"][0]["status"], "no_match")

    def test_empty_and_missing_ocr_are_distinct(self):
        self.assertEqual(interpretation.interpret_evidence(None)["status"], "not_analyzed")
        self.evidence["observations"] = []
        self.assertEqual(self.run_interpretation()["status"], "no_observations")

    def test_no_text(self):
        for row in self.evidence["observations"]:
            row.update(status="no_text", text="", words=[])
        self.assertEqual([r["status"] for r in self.run_interpretation()["interpretations"]],
                         ["no_text", "no_text"])

    def test_failed_and_unavailable_ocr_preserved(self):
        for row, status in zip(self.evidence["observations"], ("failed", "unavailable")):
            row.update(status=status, text=None, words=None, error="fixture reason")
        result = self.run_interpretation()
        self.assertEqual([r["status"] for r in result["interpretations"]], ["ocr_failed", "ocr_unavailable"])
        self.assertTrue(all(not r["hypotheses"] for r in result["interpretations"]))
        self.assertEqual(result["input_evidence"], self.evidence)

    def test_order_and_determinism(self):
        for row in self.evidence["observations"]:
            row["text"] = "you died, victory, VICTORY"
        result = self.run_interpretation()
        self.assertEqual(result, self.run_interpretation())
        self.assertEqual([r["observation_id"] for r in result["interpretations"]],
                         [r["observation_id"] for r in self.evidence["observations"]])
        self.assertEqual([h["text_span"][0] for h in result["interpretations"][0]["hypotheses"]], [0, 10, 19])

    def test_invalid_profiles(self):
        profile = interpretation.default_profile()
        cases = [dict(profile, schema_version=True), dict(profile, patterns="bad"),
                 dict(profile, patterns=[profile["patterns"][0]]*2),
                 dict(profile, patterns=[dict(id="x", event_type="kill", phrase=" ")])]
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                self.run_interpretation(profile=case)
        with self.assertRaises(ValueError):
            self.run_interpretation(game="bedwars", profile=profile)

    def test_invalid_schema_identity_and_missing_fields(self):
        cases = [dict(self.evidence, schema_version=2), dict(self.evidence, schema_version=True),
                 dict(self.evidence, source_identity={}), dict(self.evidence, observations=None)]
        missing = deepcopy(self.evidence)
        del missing["visual_evidence_provenance"]
        cases.append(missing)
        for case in cases:
            with self.subTest(case=case), self.assertRaises(ValueError):
                interpretation.interpret_evidence(case)

    def test_invalid_timestamps(self):
        for stamp in (dict(normalized_pts=5, time_base="0/1", timestamp_seconds=.5),
                      dict(normalized_pts=5, time_base="1/0", timestamp_seconds=.5),
                      dict(normalized_pts=5, time_base="1/10", timestamp_seconds=float("nan")),
                      dict(normalized_pts=110, time_base="1/10", timestamp_seconds=11),
                      dict(normalized_pts=-5, time_base="1/10", timestamp_seconds=-.5)):
            bad = deepcopy(self.evidence)
            bad["observations"][0]["timestamp"] = stamp
            with self.subTest(stamp=stamp), self.assertRaises(ValueError):
                interpretation.interpret_evidence(bad)
        self.evidence["observations"][1]["timestamp"] = dict(normalized_pts=1, time_base="1/10", timestamp_seconds=.1)
        with self.assertRaises(ValueError):
            self.run_interpretation()

    def test_invalid_confidence_and_status(self):
        for confidence in (-1, 101, float("inf"), True):
            bad = deepcopy(self.evidence)
            bad["observations"][0]["words"][0]["confidence"] = confidence
            with self.subTest(confidence=confidence), self.assertRaises(ValueError):
                interpretation.interpret_evidence(bad)
        self.evidence["observations"][0]["status"] = "no_text"
        with self.assertRaises(ValueError):
            self.run_interpretation()

    def test_duplicate_ids_and_missing_crop_region(self):
        bad = deepcopy(self.evidence)
        bad["observations"][1]["observation_id"] = bad["observations"][0]["observation_id"]
        with self.assertRaises(ValueError):
            interpretation.interpret_evidence(bad)
        self.evidence["observations"][1]["region_name"] = None
        with self.assertRaises(ValueError):
            self.run_interpretation()

    def test_cli_roundtrip_no_inference_and_no_overwrite(self):
        source, output = self.root/"ocr.json", self.root/"interpreted.json"
        source.write_text(json.dumps(self.evidence), encoding="utf-8")
        before = source.read_bytes(), source.stat().st_mtime_ns
        args = ["--input", str(source), "--output", str(output)]
        with patch("subprocess.run", side_effect=AssertionError("No subprocess allowed")), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(interpretation.main(args), 0)
            first = output.read_bytes(), output.stat().st_mtime_ns
            self.assertEqual(json.loads(first[0]), self.run_interpretation())
            self.assertEqual(interpretation.main(args), 1)
            self.assertEqual((output.read_bytes(), output.stat().st_mtime_ns), first)
            self.assertEqual(interpretation.main(["--input", str(source), "--output", str(source)]), 1)
        self.assertEqual((source.read_bytes(), source.stat().st_mtime_ns), before)

    def test_cli_custom_profile_and_deterministic_serialization(self):
        source, profile = self.root/"ocr.json", self.root/"profile.json"
        source.write_text(json.dumps(self.evidence), encoding="utf-8")
        profile.write_text(json.dumps(interpretation.default_profile("bedwars")), encoding="utf-8")
        outputs = [self.root/"a.json", self.root/"b.json"]
        with contextlib.redirect_stdout(io.StringIO()):
            for output in outputs:
                self.assertEqual(interpretation.main(["--input", str(source), "--profile", str(profile),
                                                     "--output", str(output)]), 0)
        self.assertEqual(outputs[0].read_bytes(), outputs[1].read_bytes())

    def test_missing_and_malformed_input_fail_without_output(self):
        source, output = self.root/"missing.json", self.root/"output.json"
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(interpretation.main(["--input", str(source), "--output", str(output)]), 1)
            source.write_text('{"schema_version": 1, "schema_version": 1}', encoding="utf-8")
            self.assertEqual(interpretation.main(["--input", str(source), "--output", str(output)]), 1)
        self.assertFalse(output.exists())


if __name__ == "__main__":
    unittest.main()
