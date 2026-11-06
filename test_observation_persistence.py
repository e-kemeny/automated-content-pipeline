"""Persistence tests: real WAV arithmetic and mocked media orchestration."""
from array import array
from copy import deepcopy
import contextlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch
import wave

import main as producers
import observation_persistence as persistence
from candidate_evidence import build_candidate_evidence
from inspect_candidate_evidence import inspect_evidence
from shared_analysis import create_analysis, signal
from timeline_query import query_timeline


def fixture():
    media=dict(duration_seconds=7,width=160,height=90,fps=10)
    identity=dict(version=1,algorithm="sha256",digest="a"*64,size_bytes=10,media=media)
    return dict(schema_version=1,artifact_type="full-observations",
        source_identity=identity,source_video=dict(path="fixture.mp4",sha256="a"*64,size_bytes=10,**media),
        producer_sha256="b"*64,unanalyzed_modalities=list(persistence.UNANALYZED),
        audio=dict(status="analyzed",sample_rate_hz=16000,channels=1,sample_count=112000,
            amplitude_rows=[dict(second=i,volume=100.125) for i in range(7)],
            score_rows=[dict(second=5,spike=-2.25,score=97.875),dict(second=6,spike=0,score=0)],
            provenance=deepcopy(persistence.AUDIO_PROVENANCE)),
        scene_changes=dict(status="analyzed",data=[dict(time=6,score=12),dict(time=1,score=11),dict(time=1,score=11)],
                           provenance=deepcopy(persistence.SCENE_PROVENANCE)))


def write_wav(path):
    with wave.open(str(path),"wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(16000)
        wav.writeframes(array("h",[100]*112000).tobytes())


class PersistenceTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.video=self.root/"source.mp4"
        self.video.write_bytes(b"fixture")
        self.output=self.root/"observations.json"

    def test_existing_audio_return_and_print_compatibility(self):
        wav=self.root/"audio.wav"
        write_wav(wav)
        out1,out2=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out1):
            baseline=producers.analyze_audio(wav)
        captured={}
        with contextlib.redirect_stdout(out2):
            observed=producers.analyze_audio(wav,observation_sink=captured.update)
        self.assertEqual(observed,baseline)
        self.assertEqual(out1.getvalue(),out2.getvalue())
        self.assertEqual(len(captured["volumes"]),7)
        self.assertEqual(observed,[dict(second=5,spike=0,score=100),dict(second=6,spike=0,score=100)])

    def test_scene_default_compatibility_and_strict_failure(self):
        result=subprocess.CompletedProcess(["ffmpeg"],0,"","lavfi.scd.score: 11, lavfi.scd.time: 1")
        with patch("main.subprocess.run",return_value=result) as run,contextlib.redirect_stdout(io.StringIO()):
            first=producers.analyze_video_motion("fixture.mp4")
            second=producers.analyze_video_motion("fixture.mp4",check=True)
        self.assertEqual(first,second)
        self.assertEqual(run.call_args_list[0],run.call_args_list[1])
        result.returncode=1
        result.stderr=""
        with patch("main.subprocess.run",return_value=result),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(producers.analyze_video_motion("fixture.mp4"),[])
            with self.assertRaises(subprocess.CalledProcessError):
                producers.analyze_video_motion("fixture.mp4",check=True)

    def test_identity_probe_once_and_actual_audio_rows(self):
        probe=dict(format={"duration":"7"},streams=[dict(codec_type="video",width=160,height=90,avg_frame_rate="10/1"),dict(codec_type="audio")])
        def extract(video,destination):
            write_wav(destination)
        with patch.object(persistence,"file_identity",return_value=("a"*64,7)) as hash_file,patch.object(
                persistence,"probe_format_streams",return_value=probe) as probe_file,patch.object(
                persistence,"extract_audio",side_effect=extract),patch.object(
                producers,"analyze_video_motion",return_value=[dict(time=1,score=12)]):
            result=persistence.collect_observations(self.video)
        hash_file.assert_called_once()
        probe_file.assert_called_once()
        self.assertEqual(result["source_identity"]["size_bytes"],7)
        self.assertEqual(len(result["audio"]["amplitude_rows"]),7)
        self.assertEqual(len(result["audio"]["score_rows"]),2)

    def test_values_order_duplicates_and_no_mutation(self):
        artifact=fixture()
        original=deepcopy(artifact)
        timeline=persistence.to_timeline(artifact)
        self.assertEqual(artifact,original)
        audio=[e for e in timeline["events"] if e["event_type"]=="audio_spike_score"]
        self.assertEqual(audio[0]["payload"]["spike"],-2.25)
        scenes=[e for e in timeline["events"] if e["event_type"]=="scene_change"]
        self.assertEqual([e["start_seconds"] for e in scenes],[1,1,6])
        self.assertEqual([e["source"]["row_index"] for e in scenes],[1,2,0])
        self.assertEqual(artifact["scene_changes"]["data"],original["scene_changes"]["data"])

    def test_units_cadence_and_coverage(self):
        artifact=fixture()
        persistence.validate_observations(artifact)
        provenance=artifact["audio"]["provenance"]
        self.assertEqual(provenance["cadence_seconds"],1)
        self.assertEqual(provenance["baseline_intervals"],5)
        self.assertIn("PCM",provenance["amplitude_units"])
        self.assertIn("sparse",artifact["scene_changes"]["provenance"]["temporal_coverage"])

    def test_empty_analyzed_streams_and_unanalyzed_modalities(self):
        artifact=fixture()
        artifact["audio"].update(sample_count=0,amplitude_rows=[],score_rows=[])
        artifact["scene_changes"]["data"]=[]
        timeline=persistence.to_timeline(artifact)
        self.assertEqual(timeline["events"],[])
        self.assertEqual(artifact["audio"]["status"],"analyzed")
        self.assertIn("transcript",artifact["unanalyzed_modalities"])

    def test_timeline_query_and_candidate_inspection(self):
        artifact=fixture()
        timeline=persistence.to_timeline(artifact)
        self.assertEqual(len(query_timeline(timeline,5,6)["events"]),5)
        analysis=create_analysis(artifact["source_video"])
        analysis["candidate_windows"]=signal([dict(start=5,end=6)])
        report=inspect_evidence(build_candidate_evidence(analysis,timeline))
        self.assertEqual(report["candidates"][0]["counts_by_modality"],dict(audio=4,visual=1,transcript=0))
        self.assertEqual(report["identity_comparison"],"consistent_reported_sha256")

    def test_bad_schema_numeric_and_identity(self):
        for mode in ("version","nan","identity","units","missing_rows","ordering"):
            artifact=fixture()
            if mode=="version": artifact["schema_version"]=2
            elif mode=="nan": artifact["audio"]["score_rows"][0]["score"]=float("nan")
            elif mode=="identity": artifact["source_video"]["sha256"]="c"*64
            elif mode=="units": artifact["audio"]["provenance"]["cadence_seconds"]=2
            elif mode=="missing_rows": artifact["audio"]["amplitude_rows"].pop()
            else: artifact["scene_changes"]["data"].reverse()
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                persistence.validate_observations(artifact)

    def test_missing_media(self):
        with self.assertRaises(ValueError):
            persistence.collect_observations(self.root/"missing")

    def run_cli(self,*extra):
        out,err=io.StringIO(),io.StringIO()
        with contextlib.redirect_stdout(out),contextlib.redirect_stderr(err):
            code=persistence.main(["--video",str(self.video),"--output",str(self.output),*extra])
        return code

    def test_atomic_deterministic_persistence_and_overwrite(self):
        artifact=fixture()
        with patch.object(persistence,"collect_observations",return_value=artifact) as collect:
            self.assertEqual(self.run_cli(),0)
            first=self.output.read_bytes()
            self.assertEqual(self.run_cli(),1)
            self.assertEqual(collect.call_count,1)
            self.assertEqual(self.run_cli("--overwrite"),0)
        self.assertEqual(first,self.output.read_bytes())

    def test_analysis_failure_and_interrupt_no_final_file(self):
        for error in (ValueError("analysis failed"),subprocess.CalledProcessError(1,["ffmpeg"])):
            with patch.object(persistence,"collect_observations",side_effect=error):
                self.assertEqual(self.run_cli(),1)
            self.assertFalse(self.output.exists())
        with patch.object(persistence,"collect_observations",side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.run_cli()
        self.assertFalse(self.output.exists())

    def test_failed_publication_preserves_existing(self):
        with patch.object(persistence,"collect_observations",return_value=fixture()):
            self.assertEqual(self.run_cli(),0)
            original=self.output.read_bytes()
            with patch("timeline_query.os.replace",side_effect=OSError("failure")):
                self.assertEqual(self.run_cli("--overwrite"),1)
        self.assertEqual(self.output.read_bytes(),original)
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_source_and_unrelated_output_protection(self):
        with self.assertRaises(ValueError):
            persistence.check_destination(self.video,self.video,True)
        self.output.write_text("{}")
        with patch.object(persistence,"collect_observations",side_effect=AssertionError("must not analyze")):
            self.assertEqual(self.run_cli("--overwrite"),1)

    def test_saved_artifact_adapter_no_reanalysis(self):
        self.output.write_text(json.dumps(fixture()))
        timeline=self.root/"timeline.json"
        with patch.object(persistence,"collect_observations",side_effect=AssertionError("analysis")),contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(persistence.main(["--timeline-from",str(self.output),"--output",str(timeline)]),0)
        self.assertEqual(json.loads(timeline.read_text())["timeline_type"],"multimodal-observations")

    def test_import_safety(self):
        code="""import sys
def audit(event,args):
    if event in ('subprocess.Popen','os.mkdir','os.remove'):
        raise AssertionError(event)
    if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or args[2] & 3):
        raise AssertionError('write')
sys.addaudithook(audit)
import observation_persistence
assert not any(name in sys.modules for name in ('torch','transformers','faster_whisper'))
"""
        result=subprocess.run([sys.executable,"-B","-c",code],capture_output=True,text=True,cwd=Path(persistence.__file__).parent)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout+result.stderr,"")


if __name__=="__main__":
    unittest.main()
