"""Synthetic fixtures for extraction, profiles, PTS and safe publication."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import visual_evidence as visual


def png(path,width,height):
    path.write_bytes(b"\x89PNG\r\n\x1a\n"+struct.pack(">I",13)+b"IHDR"+struct.pack(">II",width,height)+b"mock")


class ProfileTests(unittest.TestCase):
    def test_generic(self):
        profile,fallback=visual.load_profile()
        self.assertEqual(profile["game_id"],"generic")
        self.assertEqual(len(profile["regions"]),1)
        self.assertFalse(fallback)

    def test_bedwars(self):
        profile,fallback=visual.load_profile("bedwars")
        self.assertEqual(len(profile["regions"]),4)
        self.assertFalse(fallback)

    def test_unknown_game_fallback(self):
        self.assertEqual(visual.load_profile("unrecognized-game")[0],visual.load_profile()[0])
        self.assertTrue(visual.load_profile("unrecognized-game")[1])

    def test_invalid_profiles(self):
        for field,value in (("schema_version",2),("profile_version",True),("game_id",""),("ui_hints",[]),("regions",[])):
            profile=visual.load_profile()[0]
            profile[field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                visual.validate_profile(profile)

    def test_invalid_regions(self):
        for field,value in (("x",-1),("y",1),("width",0),("height",2),("x",float("nan")),
                             ("width",True),("name","../escape"),("name","")):
            profile=visual.load_profile()[0]
            profile["regions"][0][field]=value
            with self.subTest(field=field),self.assertRaises(ValueError):
                visual.validate_profile(profile)
        profile=visual.load_profile()[0]
        profile["regions"]*=2
        with self.assertRaises(ValueError):
            visual.validate_profile(profile)

    def test_custom_profile_and_conflicting_options(self):
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/"profile.json"
            profile=visual.load_profile()[0]
            profile["game_id"]="custom-game"
            path.write_text(json.dumps(profile))
            self.assertEqual(visual.load_profile(profile_path=path)[0],profile)
            with self.assertRaises(ValueError):
                visual.load_profile(game="bedwars",profile_path=path)

    def test_crop_rounding(self):
        region=dict(name="corner",x=.25,y=.75,width=.5,height=.25)
        self.assertEqual(visual.crop_geometry(region,80,46),dict(x=20,y=34,width=40,height=12))

    def test_configuration_limits(self):
        for kwargs in (dict(interval=0),dict(start=-1),dict(end=11),dict(start=5,end=4),
                       dict(max_frames=0),dict(max_frames=1001),dict(width=True),dict(height=4097),
                       dict(interval=float("inf")),dict(end=float("nan"))):
            with self.subTest(kwargs=kwargs),self.assertRaises(ValueError):
                visual.configuration(10,**kwargs)
        self.assertEqual(visual.configuration(10,start=10,end=10)["end_seconds"],10)


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.video=self.root/"video.mp4"
        self.video.write_bytes(b"synthetic mocked source")
        self.destination=self.root/"new-output"
        self.media=dict(duration_seconds=3,width=160,height=90,stream_index=0)

    def fake_frames(self,video,index,stage,config):
        png(stage/"sample_000001.png",config["width"],config["height"])
        (stage/"extraction.log").write_text("synthetic extraction")
        return [dict(normalized_pts=500,time_base="1/1000",timestamp_seconds=.5)],"fixture-filter"

    def fake_crop(self,frame,target,rectangle):
        png(target,rectangle["width"],rectangle["height"])

    def extract(self,**kwargs):
        with patch.object(visual,"inspect_video",return_value=self.media),patch.object(
                visual,"extract_frames",side_effect=self.fake_frames),patch.object(
                visual,"extract_crop",side_effect=self.fake_crop),patch.object(
                visual.subprocess,"run",return_value=SimpleNamespace(stdout="ffmpeg fixture\n")):
            return visual.extract_evidence(self.video,self.destination,width=80,height=46,**kwargs)

    def test_frames_hashes_relative_paths_identity_and_determinism(self):
        first=self.extract()
        frame=first["frames"][0]
        path=self.destination/frame["image_path"]
        self.assertFalse(Path(frame["image_path"]).is_absolute())
        self.assertEqual(frame["sha256"],hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(first["source_identity"]["digest"],hashlib.sha256(self.video.read_bytes()).hexdigest())
        self.assertEqual(first["source_identity"]["media"]["width"],160)
        self.assertEqual(frame["width"],80)
        self.destination=self.root/"second-output"
        self.assertEqual(first,self.extract())

    def test_crops_include_parent_coordinates_and_hashes(self):
        result=self.extract(game="bedwars",crops=True)
        row=result["frames"][0]
        self.assertEqual(len(row["regions"]),4)
        for crop in row["regions"]:
            self.assertEqual(crop["parent_frame_id"],row["frame_id"])
            self.assertEqual(crop["sha256"],hashlib.sha256((self.destination/crop["image_path"]).read_bytes()).hexdigest())
            self.assertEqual(visual.png_dimensions(self.destination/crop["image_path"]),(crop["width"],crop["height"]))

    def test_expected_identity_conflict(self):
        identity=dict(version=1,algorithm="sha256",digest="a"*64,size_bytes=1,
                      media=dict(duration_seconds=3,width=160,height=90))
        with self.assertRaisesRegex(ValueError,"Conflicting"):
            self.extract(expected_identity=identity)
        self.assertFalse(self.destination.exists())

    def test_missing_video(self):
        self.video.unlink()
        with self.assertRaises(OSError):
            visual.extract_evidence(self.video,self.destination)

    def test_source_mutation_fails(self):
        original=self.fake_frames
        def changed(*args):
            result=original(*args)
            self.video.write_bytes(b"changed content")
            return result
        self.fake_frames=changed
        with self.assertRaisesRegex(ValueError,"Source content changed"):
            self.extract()
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".visual-evidence-*")))

    def test_existing_output_and_production_isolation(self):
        self.destination.mkdir()
        sentinel=self.destination/"keep.txt"
        sentinel.write_text("keep")
        with patch.object(visual,"inspect_video",side_effect=AssertionError("no probe")):
            with self.assertRaises(FileExistsError):
                self.extract()
            with self.assertRaises(ValueError):
                visual.extract_evidence(self.video,visual.ROOT/"output"/"my_recording"/"bad")
        self.assertEqual(sentinel.read_text(),"keep")

    def test_ffmpeg_failure_cleanup(self):
        def failed(*args):
            raise subprocess.CalledProcessError(1,["ffmpeg"])
        self.fake_frames=failed
        with self.assertRaises(subprocess.CalledProcessError):
            self.extract()
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".visual-evidence-*")))

    def test_zero_frame_range_does_not_decode(self):
        def forbidden(*args):
            raise AssertionError("No extraction on empty range")
        self.fake_frames=forbidden
        result=self.extract(start=3,end=3)
        self.assertEqual(result["frames"],[])
        self.assertEqual(result["coverage"]["status"],"no_frames")

    def test_no_decodable_frames(self):
        self.fake_frames=lambda *args:([],"fixture")
        self.assertEqual(self.extract()["coverage"]["frame_count"],0)

    def test_timestamp_image_mismatch_cleanup(self):
        def mismatch(*args):
            self.fake_frames_original(*args)
            return [],"fixture"
        self.fake_frames_original=self.fake_frames
        self.fake_frames=mismatch
        with self.assertRaisesRegex(ValueError,"disagree"):
            self.extract()
        self.assertFalse(self.destination.exists())

    def test_output_publication_failure(self):
        rename = visual.os.rename
        def fail_publication(source,target):
            if Path(target)==self.destination:
                self.assertTrue((Path(source)/"visual_evidence_manifest.json").is_file())
                raise OSError("publication failed")
            return rename(source,target)
        with patch.object(visual.os,"rename",side_effect=fail_publication):
            with self.assertRaises(OSError):
                self.extract()
        self.assertFalse(self.destination.exists())
        self.assertFalse(list(self.root.glob(".visual-evidence-*")))

    def test_timestamp_parser_uses_integer_pts_not_rounded_display(self):
        log=self.root/"pts.log"
        log.write_text("[Parsed_showinfo_4] config in time_base: 1/1000, frame_rate: 4/1\n"
                       "[Parsed_showinfo_4] n: 0 pts: 500 pts_time:0.499999\n"
                       "[Parsed_showinfo_4] n: 1 pts: 1000 pts_time:1\n")
        result=visual.parse_timestamps(log)
        self.assertEqual([r["timestamp_seconds"] for r in result],[.5,1])

    def test_invalid_pts_metadata(self):
        for text in ("[showinfo] n: 0 pts: 1 pts_time:1",
                     "[showinfo] config in time_base: 1/0\n",
                     "[showinfo] config in time_base: 1/10\n[showinfo] n: 1 pts: 2 pts_time:.2",
                     "[showinfo] config in time_base: 1/10\n[showinfo] n: 0 pts: -1 pts_time:-.1",
                     "[showinfo] config in time_base: 1/10\n[showinfo] n: 0 pts: 1 pts_time:.1\n[showinfo] n: 1 pts: 1 pts_time:.1"):
            log=self.root/"pts.log"
            log.write_text(text)
            with self.subTest(text=text),self.assertRaises(ValueError):
                visual.parse_timestamps(log)

    def test_invalid_png(self):
        with self.assertRaises(ValueError):
            visual.png_dimensions(self.video)

    def test_exact_decoder_command_and_timeout(self):
        config=visual.configuration(3,start=.3,end=2,max_frames=3,width=80,height=46)
        def run(cmd,**kwargs):
            self.assertIn("-copyts",cmd)
            self.assertNotIn("-ss",cmd)
            self.assertNotIn("-r",cmd)
            self.assertEqual(cmd[cmd.index("-fps_mode")+1],"passthrough")
            self.assertIn("trim=end_frame=3",cmd[cmd.index("-vf")+1])
            self.assertEqual(kwargs["timeout"],600)
        with patch.object(visual.subprocess,"run",side_effect=run):
            rows,filters=visual.extract_frames(self.video,0,self.root,config)
        self.assertEqual(rows,[])
        self.assertIn("setpts=PTS-STARTPTS",filters)

    def test_cli_forwarding_and_errors(self):
        args=["--video",str(self.video),"--output-root",str(self.destination),"--game","unknown","--crops","--max-frames","2"]
        with contextlib.redirect_stdout(io.StringIO()),patch.object(visual,"extract_evidence",return_value={"frames":[]}) as run:
            self.assertEqual(visual.main(args),0)
            self.assertEqual(run.call_args.kwargs["max_frames"],2)
            self.assertTrue(run.call_args.kwargs["crops"])
        with contextlib.redirect_stderr(io.StringIO()),patch.object(visual,"extract_evidence",side_effect=ValueError("bad source")):
            self.assertEqual(visual.main(args),1)

    def test_import_safety(self):
        code="""import sys
def audit(event,args):
    if event in ('subprocess.Popen','os.mkdir','os.remove'):
        raise AssertionError(event)
    if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or args[2] & 3):
        raise AssertionError('write')
sys.addaudithook(audit)
import visual_evidence
assert not any(m in sys.modules for m in ('torch','torchvision','PIL','transformers'))
"""
        result=subprocess.run([sys.executable,"-B","-c",code],cwd=visual.ROOT,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout+result.stderr,"")


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"),"Synthetic media check requires FFmpeg/FFprobe")
class SyntheticVideoTests(unittest.TestCase):
    def test_measured_pts_crops_and_cap(self):
        with tempfile.TemporaryDirectory(prefix="visual-evidence-test-") as directory:
            root=Path(directory)
            source=root/"synthetic.mkv"
            subprocess.run(["ffmpeg","-v","error","-nostdin","-n","-f","lavfi","-i","testsrc2=size=160x90:rate=4",
                "-t","3","-c:v","libx264",str(source)],check=True,capture_output=True)
            result=visual.extract_evidence(source,root/"frames",start=.3,end=2.1,interval=.5,
                                           max_frames=3,width=80,height=46,game="bedwars",crops=True)
            self.assertEqual([r["timestamp_seconds"] for r in result["frames"]],[.5,1,1.5])
            self.assertTrue(result["coverage"]["max_frame_limit_reached"])
            probe=subprocess.run(["ffprobe","-v","error","-select_streams","v:0","-show_entries",
                "frame=best_effort_timestamp_time","-of","json",str(source)],check=True,capture_output=True,text=True)
            decoded=[float(f["best_effort_timestamp_time"]) for f in json.loads(probe.stdout)["frames"]]
            for row in result["frames"]:
                self.assertIn(row["timestamp_seconds"],decoded)
                self.assertEqual(len(row["regions"]),4)
                self.assertTrue((root/"frames"/row["image_path"]).is_file())


if __name__=="__main__":
    unittest.main()
