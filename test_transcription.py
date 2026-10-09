"""Mocked ASR and CLI tests: no model downloads or inference."""
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest.mock import Mock, patch
from shared_analysis import create_analysis, load_analysis, save_analysis, signal
import transcription as asr
import transcribe_video as cli

class TranscriptionTests(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.media = self.root/"video.mp4"
        self.media.write_bytes(b"fixture")
        self.source = dict(path=str(self.media.resolve()), duration_seconds=20, sha256=asr.media_sha256(self.media))
        self.path = self.root/"analysis.json"
        self.analysis = create_analysis(self.source)
        self.analysis["visual"]["scene_changes"] = signal([dict(time=2, score=3)])
        self.analysis["candidate_windows"] = signal([dict(second=5, start=0, end=10, duration=10)])
        self.analysis["language"]["reaction"] = signal([dict(start=1, end=2, note="preserve")])
        save_analysis(self.analysis, self.path)
        self.rows = [dict(start=1.2, end=2.5, text=" Hello."), dict(start=3, end=4, text="World!")]
        self.provenance = dict(model="small.en", language="en", device="cpu", compute_type="int8",
            processing_seconds=1.5, source_sha256=self.source["sha256"], source_duration_seconds=20)
        self.result = dict(segments=self.rows, provenance=self.provenance)

    def update(self, **kwargs):
        with patch.object(cli, "probe_media", return_value=self.source), patch.object(cli, "transcribe_media", return_value=self.result) as backend:
            result = cli.update_transcript(self.media, self.path, **kwargs)
        return result, backend

    def run_backend(self, segments, failure=None):
        model = Mock()
        model.transcribe.return_value = (iter(segments), NS(language="en"))
        with patch.object(asr, "probe_media", return_value=self.source), patch.object(asr, "extract_audio") as extract, patch.object(asr, "load_model", return_value=(model, self.provenance), side_effect=failure) as initialize:
            result = asr.transcribe_media(self.media, work_dir=self.root/"work", cache_dir=self.root/"models", word_timestamps=True)
        initialize.assert_called_once_with(self.root/"models", "cpu", "int8")
        self.assertTrue(model.transcribe.call_args.kwargs["vad_filter"])
        self.assertNotEqual(Path(extract.call_args.args[1]), self.media)
        self.assertEqual(list((self.root/"work").iterdir()), [])
        return result

    def test_success_multiple_segments_and_provenance(self):
        words = [NS(start=1.2, end=2, word=" Hello", probability=0.8)]
        result = self.run_backend([NS(**self.rows[0], words=words), NS(**self.rows[1], words=None)])
        self.assertEqual(result["segments"][0]["text"], " Hello.")
        self.assertEqual(result["segments"][1], self.rows[1])
        self.assertEqual(result["segments"][0]["metadata"]["words"][0]["probability"], 0.8)
        self.assertNotIn("confidence", result["segments"][0])
        self.assertEqual(result["provenance"]["language"], "en")
        self.assertGreaterEqual(result["provenance"]["processing_seconds"], 0)

    def test_silence(self):
        self.assertEqual(self.run_backend([])["segments"], [])

    def test_invalid_timestamps_bounds_order_words(self):
        for start, end in [(-1,2),(3,2),(0,21),(float("nan"),2),(0,float("inf")),(True,2),("1",2)]:
            with self.subTest(start=start), self.assertRaises(ValueError):
                asr.validate_segments([dict(start=start,end=end,text="x")],20)
        with self.assertRaises(ValueError):
            asr.validate_segments(list(reversed(self.rows)),20)
        with self.assertRaises(ValueError):
            asr.validate_segments([dict(start=1,end=2,text="x",metadata=dict(words=[dict(start=0,end=1,word="x")]))],20)

    def test_rows_not_mutated(self):
        before = deepcopy(self.rows)
        asr.validate_segments(self.rows,20)[0]["text"] = "changed"
        self.assertEqual(before,self.rows)

    def test_missing_input_no_inference(self):
        with patch.object(asr,"load_model") as model, self.assertRaises(FileNotFoundError):
            asr.transcribe_media(self.root/"missing")
        model.assert_not_called()

    def test_initialization_failure_cleanup(self):
        with self.assertRaisesRegex(RuntimeError,"initialize small.en"):
            self.run_backend([], ImportError("missing"))
        self.assertEqual(list((self.root/"work").iterdir()),[])

    def test_safe_extraction(self):
        with self.assertRaises(FileExistsError):
            asr.extract_audio(self.media,self.media)
        with patch.object(asr.subprocess,"run") as run:
            asr.extract_audio(self.media,self.root/"audio.wav")
        command=run.call_args.args[0]
        self.assertIn("-n",command)
        self.assertEqual(command[command.index("-ar")+1],"16000")
        self.assertEqual(command[command.index("-ac")+1],"1")

    def test_probe_actual_metadata(self):
        data=dict(format=dict(duration="20"),streams=[dict(codec_type="video",width=160,height=90,avg_frame_rate="30/1"),dict(codec_type="audio")])
        with patch.object(asr.subprocess,"run",return_value=NS(stdout=json.dumps(data))):
            source=asr.probe_media(self.media)
        self.assertEqual(source["fps"],30)
        self.assertEqual(source["sha256"],self.source["sha256"])

    def test_preservation_deterministic_roundtrip(self):
        (updated,reused),backend=self.update()
        backend.assert_called_once()
        self.assertFalse(reused)
        for key in self.analysis:
            if key!="transcript":
                self.assertEqual(updated[key],self.analysis[key])
        self.assertEqual(updated["transcript"],signal(self.rows,self.provenance))
        self.assertEqual(load_analysis(self.path),updated)
        before=self.path.read_bytes()
        save_analysis(load_analysis(self.path),self.path)
        self.assertEqual(before,self.path.read_bytes())

    def test_cache_empty_or_populated_no_inference_probe_write(self):
        for rows in [self.rows,[]]:
            self.analysis["transcript"]=signal(rows,self.provenance)
            save_analysis(self.analysis,self.path)
            before=self.path.read_bytes()
            with patch.object(cli,"transcribe_media") as backend,patch.object(cli,"probe_media") as probe:
                _,reused=cli.update_transcript(self.media,self.path)
            self.assertTrue(reused)
            backend.assert_not_called()
            probe.assert_not_called()
            self.assertEqual(before,self.path.read_bytes())

    def test_force_only_transcript(self):
        self.analysis["transcript"]=signal([],self.provenance)
        save_analysis(self.analysis,self.path)
        (updated,reused),backend=self.update(force=True)
        backend.assert_called_once()
        self.assertFalse(reused)
        for key in self.analysis:
            if key!="transcript":
                self.assertEqual(updated[key],self.analysis[key])

    def test_incompatible_schema_no_inference(self):
        bad=deepcopy(self.analysis)
        bad["schema_version"]=99
        self.path.write_text(json.dumps(bad))
        with patch.object(cli,"transcribe_media") as backend,self.assertRaises(ValueError):
            cli.update_transcript(self.media,self.path)
        backend.assert_not_called()

    def test_identity_mismatch_no_inference(self):
        self.analysis["source_video"]["sha256"]="0"*64
        save_analysis(self.analysis,self.path)
        with patch.object(cli,"transcribe_media") as backend,self.assertRaisesRegex(ValueError,"identity"):
            cli.update_transcript(self.media,self.path)
        backend.assert_not_called()
        with self.assertRaises(ValueError):
            cli.verify_source(dict(path=str(self.root/"other"),duration_seconds=20),self.media.resolve(),"hash")

    def test_duration_mismatch_before_inference(self):
        with patch.object(cli,"probe_media",return_value=dict(self.source,duration_seconds=21)),patch.object(cli,"transcribe_media") as backend,self.assertRaisesRegex(ValueError,"duration"):
            cli.update_transcript(self.media,self.path)
        backend.assert_not_called()

    def test_failure_preserves_document(self):
        before=self.path.read_bytes()
        with patch.object(cli,"probe_media",return_value=self.source),patch.object(cli,"transcribe_media",side_effect=RuntimeError("failure")),self.assertRaises(RuntimeError):
            cli.update_transcript(self.media,self.path)
        self.assertEqual(before,self.path.read_bytes())

    def test_source_changed_during_inference(self):
        self.result["provenance"]["source_sha256"]="changed"
        before=self.path.read_bytes()
        with self.assertRaisesRegex(ValueError,"Source changed"):
            self.update()
        self.assertEqual(before,self.path.read_bytes())

    def test_explicit_create_no_fabricated_evidence(self):
        self.path.unlink()
        with self.assertRaises(FileNotFoundError):
            cli.update_transcript(self.media,self.path)
        (result,reused),_=self.update(create=True)
        self.assertFalse(reused)
        self.assertEqual(result["source_video"],self.source)
        self.assertTrue(all(s["status"]=="not_analyzed" for s in result["visual"].values()))
        self.assertEqual(result["candidate_windows"]["status"],"not_analyzed")

    def test_cli_flags_output(self):
        result=deepcopy(self.analysis)
        result["transcript"]=signal(self.rows,self.provenance)
        with patch.object(cli,"update_transcript",return_value=(result,False)) as update,contextlib.redirect_stdout(io.StringIO()) as output:
            cli.main([str(self.media),"--analysis",str(self.path),"--force","--create","--word-timestamps"])
        for key in ["force","create","word_timestamps"]:
            self.assertTrue(update.call_args.kwargs[key])
        self.assertIn("Saved 2",output.getvalue())

    def test_cli_error(self):
        with patch.object(cli,"update_transcript",side_effect=RuntimeError("broken")),contextlib.redirect_stderr(io.StringIO()) as errors,self.assertRaises(SystemExit) as exit:
            cli.main([str(self.media),"--analysis",str(self.path)])
        self.assertEqual(exit.exception.code,1)
        self.assertIn("broken",errors.getvalue())

if __name__=="__main__":
    unittest.main()
