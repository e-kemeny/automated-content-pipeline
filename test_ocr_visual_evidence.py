"""Synthetic PNG bundles and injected OCR backends; no real OCR required."""
from copy import deepcopy
import contextlib
import hashlib
import io
import json
from pathlib import Path
import struct
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
import zlib

import ocr_visual_evidence as ocr
from visual_evidence import TIME_BASIS, configuration, load_profile


def png_bytes():
    def chunk(kind,data):
        return struct.pack(">I",len(data))+kind+data+struct.pack(">I",zlib.crc32(kind+data)&0xffffffff)
    return (b"\x89PNG\r\n\x1a\n"+chunk(b"IHDR",struct.pack(">IIBBBBB",16,10,8,2,0,0,0))+
            chunk(b"IDAT",zlib.compress((b"\0"+b"\xff"*48)*10))+chunk(b"IEND",b""))


def bundle(root,crops=True):
    identity=dict(version=1,algorithm="sha256",digest="a"*64,size_bytes=123,
                  media=dict(duration_seconds=10,width=160,height=100))
    timing=dict(normalized_pts=5,time_base="1/10",timestamp_seconds=.5)
    frame_id=ocr.digest(dict(source=identity,timing=timing,width=16,height=10))
    data=png_bytes()
    sha=hashlib.sha256(data).hexdigest()
    (root/"frame.png").write_bytes(data)
    regions=[]
    profile=load_profile()[0]
    if crops:
        (root/"crop.png").write_bytes(data)
        regions=[dict(parent_frame_id=frame_id,region_name="full_frame",image_path="crop.png",
            normalized_region=profile["regions"][0],pixel_rectangle=dict(x=0,y=0,width=16,height=10),
            width=16,height=10,sha256=sha)]
    manifest=dict(schema_version=1,artifact_type="visual-evidence",source_identity=identity,source_location="fixture.mp4",
        video_duration_seconds=10,sampling=configuration(10,width=16,height=10),profile=profile,
        requested_game=None,unknown_game_fallback=False,crops_enabled=crops,
        frames=[dict(frame_id=frame_id,**timing,image_path="frame.png",width=16,height=10,sha256=sha,regions=regions)],
        extraction_provenance=dict(time_basis=TIME_BASIS,ffmpeg_version="fixture",stream_index=0,filter="fixture",log=None),
        coverage=dict(frame_count=1,status="sampled",max_frame_limit_reached=False,temporal_coverage="unknown"),limitations=[])
    path=root/"visual_evidence_manifest.json"
    path.write_text(json.dumps(manifest),encoding="utf-8")
    return path,manifest


class FakeBackend:
    identifier="fake-test-only"
    def __init__(self,result=None,status="available"):
        self.calls=[]
        self.result=result if result is not None else dict(text="FIXTURE",words=[dict(text="FIXTURE",bbox=dict(x=1,y=1,width=8,height=3))])
        self.status=status

    def check(self,language):
        return dict(identifier=self.identifier,version="test-v1",status=self.status,
                    reason=None if self.status=="available" else "test unavailable")

    def recognize(self,path,language,psm):
        self.calls.append((path,language,psm))
        if isinstance(self.result,Exception):
            raise self.result
        return deepcopy(self.result)


TSV="level\tpage_num\tblock_num\tpar_num\tline_num\tword_num\tleft\ttop\twidth\theight\tconf\ttext\n"


class BackendTests(unittest.TestCase):
    def test_missing_executable(self):
        with patch.object(ocr.shutil,"which",return_value=None),patch.object(ocr.subprocess,"run") as run:
            info=ocr.TesseractBackend().check("eng")
        self.assertEqual(info["status"],"unavailable")
        self.assertIsNone(info["version"])
        run.assert_not_called()

    def test_available_version_language_and_command(self):
        backend=ocr.TesseractBackend("custom executable")
        outputs=[SimpleNamespace(stdout="tesseract 5.test\n"),SimpleNamespace(stdout="List of available languages (1):\neng\n")]
        with patch.object(ocr.shutil,"which",return_value="custom executable"),patch.object(ocr.subprocess,"run",side_effect=outputs):
            self.assertEqual(backend.check("eng")["status"],"available")
        with patch.object(ocr.subprocess,"run",return_value=SimpleNamespace(stdout=TSV)) as run:
            self.assertEqual(backend.recognize(Path("fixture.png"),"eng",3),dict(text="",words=[]))
        self.assertEqual(run.call_args.args[0],["custom executable","fixture.png","-","-l","eng","--psm","3","tsv"])
        self.assertEqual(run.call_args.kwargs["timeout"],60)

    def test_missing_language(self):
        with patch.object(ocr.shutil,"which",return_value="tesseract"),patch.object(
                ocr.subprocess,"run",side_effect=[SimpleNamespace(stdout="tesseract 5\n"),SimpleNamespace(stdout="eng\n")]):
            self.assertEqual(ocr.TesseractBackend().check("deu")["status"],"unavailable")

    def test_backend_probe_failures(self):
        for failure in (OSError("missing"),subprocess.TimeoutExpired("tesseract",10),subprocess.CalledProcessError(1,"tesseract")):
            with patch.object(ocr.shutil,"which",return_value="tesseract"),patch.object(
                    ocr.subprocess,"run",side_effect=failure):
                self.assertEqual(ocr.TesseractBackend().check("eng")["status"],"failed")

    def test_tsv_text_boxes_and_native_confidence(self):
        text=TSV+"1\t1\t0\t0\t0\t0\t0\t0\t16\t10\t-1\t\n"+"5\t1\t1\t1\t1\t1\t1\t1\t8\t3\t91.25\tHELLO\n"
        result=ocr.validate_result(ocr.parse_tsv(text),16,10)
        self.assertEqual(result["text"],"HELLO")
        self.assertEqual(result["words"][0]["confidence"],91.25)
        unknown=ocr.parse_tsv(text.replace("91.25","-1"))
        self.assertNotIn("confidence",unknown["words"][0])

    def test_invalid_tsv(self):
        for text in ("", "bad header\n",TSV+"5\t1\n",TSV+"5\t1\t1\t1\t1\t1\t0\t0\t1\t1\tNaN\tTEXT\n",
                     TSV+"6\t1\t1\t1\t1\t1\t0\t0\t1\t1\t90\tTEXT\n"):
            with self.subTest(text=text),self.assertRaises(ValueError):
                ocr.parse_tsv(text)

    def test_confidence_and_bbox_validation(self):
        for changes in (dict(confidence=True),dict(confidence=float("inf")),dict(confidence=-1),dict(confidence=101),
                        dict(bbox=dict(x=-1,y=0,width=1,height=1)),dict(bbox=dict(x=15,y=0,width=2,height=1)),
                        dict(bbox=dict(x=0,y=0,width=0,height=1))):
            word=dict(text="word",**changes)
            with self.subTest(changes=changes),self.assertRaises(ValueError):
                ocr.validate_result(dict(text="word",words=[word]),16,10)


class BundleTests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.path,self.manifest=bundle(self.root)

    def save(self):
        self.path.write_text(json.dumps(self.manifest),encoding="utf-8")

    def test_modes_reuse_and_parent_relationship(self):
        for mode,count in (("full",1),("crops",1),("both",2)):
            backend=FakeBackend()
            result=ocr.recognize_bundle(self.path,mode=mode,backend=backend)
            self.assertEqual(len(result["observations"]),count)
            self.assertEqual(len(backend.calls),1)
            self.assertEqual(result["status"],"completed")
        rows=result["observations"]
        self.assertEqual([r["kind"] for r in rows],["full","crop"])
        self.assertEqual(rows[1]["parent_frame_id"],rows[0]["parent_frame_id"])
        self.assertEqual(rows[1]["reused_from"],rows[0]["observation_id"])

    def test_success_no_text_not_unavailable(self):
        result=ocr.recognize_bundle(self.path,backend=FakeBackend(dict(text="",words=[])))
        self.assertEqual(result["counts"]["no_text"],2)
        result=ocr.recognize_bundle(self.path,backend=FakeBackend(status="unavailable"))
        self.assertEqual(result["status"],"unavailable")
        self.assertIsNone(result["observations"][0]["text"])
        self.assertIsNone(result["observations"][0]["words"])

    def test_backend_failure_and_bad_output(self):
        for result in (RuntimeError("engine failed"),dict(text="x",words=[dict(text="x",confidence=1000)])):
            report=ocr.recognize_bundle(self.path,backend=FakeBackend(result))
            self.assertEqual(report["status"],"failed")
            self.assertIsNone(report["observations"][0]["text"])
            self.assertTrue(report["observations"][0]["error"])

    def test_empty_crops(self):
        self.manifest["crops_enabled"]=False
        self.manifest["frames"][0]["regions"]=[]
        self.save()
        backend=FakeBackend()
        result=ocr.recognize_bundle(self.path,mode="crops",backend=backend)
        self.assertEqual(result["status"],"no_inputs")
        self.assertEqual(result["observations"],[])
        self.assertEqual(backend.calls,[])
        self.assertEqual(result["coverage"]["available_crops"],0)

    def test_timestamp_identity_provenance_and_determinism(self):
        before={p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.iterdir()}
        one=ocr.recognize_bundle(self.path,backend=FakeBackend())
        two=ocr.recognize_bundle(self.path,backend=FakeBackend())
        self.assertEqual(one,two)
        self.assertEqual(one["source_identity"],self.manifest["source_identity"])
        self.assertEqual(one["observations"][0]["timestamp"],dict(normalized_pts=5,time_base="1/10",timestamp_seconds=.5))
        self.assertEqual(one["visual_evidence_provenance"]["manifest"],self.manifest)
        self.assertEqual(before,{p:(p.read_bytes(),p.stat().st_mtime_ns) for p in self.root.iterdir()})

    def test_traversal_and_absolute_paths(self):
        for name in ("../frame.png","/frame.png","C:/frame.png","C:frame.png","\\\\server\\share\\x.png",
                     "folder/../../frame.png","folder\\frame.png","./frame.png","frame.png:stream"):
            self.manifest["frames"][0]["image_path"]=name
            self.save()
            with self.subTest(name=name),self.assertRaises(ValueError):
                ocr.recognize_bundle(self.path,backend=FakeBackend())

    def test_safe_nested_path(self):
        (self.root/"nested").mkdir()
        (self.root/"nested"/"frame.png").write_bytes((self.root/"frame.png").read_bytes())
        self.manifest["frames"][0]["image_path"]="nested/frame.png"
        self.save()
        self.assertEqual(ocr.recognize_bundle(self.path,backend=FakeBackend())["status"],"completed")

    def test_hash_mismatch_before_backend(self):
        (self.root/"crop.png").write_bytes(b"changed")
        backend=FakeBackend()
        with patch.object(backend,"check",side_effect=AssertionError("must validate inputs first")):
            with self.assertRaisesRegex(ValueError,"SHA-256"):
                ocr.recognize_bundle(self.path,mode="full",backend=backend)

    def test_malformed_manifest_bounds_crop_and_identity(self):
        original=deepcopy(self.manifest)
        for mode in ("schema","duration","timestamp","timebase","parent","crop","frameid"):
            self.manifest=deepcopy(original)
            if mode=="schema": self.manifest["schema_version"]=2
            elif mode=="duration": self.manifest["video_duration_seconds"]=12
            elif mode=="timestamp": self.manifest["frames"][0]["timestamp_seconds"]=.6
            elif mode=="timebase": self.manifest["frames"][0]["time_base"]="1/0"
            elif mode=="parent": self.manifest["frames"][0]["regions"][0]["parent_frame_id"]="bad"
            elif mode=="crop": self.manifest["frames"][0]["regions"][0]["pixel_rectangle"]["x"]=1
            else: self.manifest["frames"][0]["frame_id"]="bad"
            self.save()
            with self.subTest(mode=mode),self.assertRaises(ValueError):
                ocr.load_bundle(self.path)

    def test_profile_hints_and_override(self):
        self.manifest["profile"]["ui_hints"]["ocr"]=dict(language="eng",psm=6,preferred_regions=[])
        self.save()
        backend=FakeBackend()
        result=ocr.recognize_bundle(self.path,backend=backend,psm=7)
        self.assertEqual(len(result["observations"]),1)
        self.assertEqual(backend.calls[0][2],7)
        for hints in (dict(language="../eng"),dict(psm=0),dict(preferred_regions=["missing"]),dict(unknown=True)):
            profile=deepcopy(self.manifest["profile"])
            profile["ui_hints"]["ocr"]=hints
            with self.assertRaises(ValueError):
                ocr.settings_for(profile)

    def test_input_mutation_detection(self):
        backend=FakeBackend()
        def mutate(*args):
            (self.root/"frame.png").write_bytes(b"changed")
            return dict(text="",words=[])
        backend.recognize=mutate
        with self.assertRaisesRegex(ValueError,"changed during OCR"):
            ocr.recognize_bundle(self.path,backend=backend)

    def test_backend_check_exception(self):
        backend=FakeBackend()
        with patch.object(backend,"check",side_effect=RuntimeError("probe failed")):
            self.assertEqual(ocr.recognize_bundle(self.path,backend=backend)["status"],"failed")

    def test_partial_failure(self):
        # Distinct valid image bytes avoid reuse, retaining the same dimensions.
        crop=self.root/"crop.png"
        crop.write_bytes(crop.read_bytes()+b"distinct trailing fixture data")
        self.manifest["frames"][0]["regions"][0]["sha256"]=hashlib.sha256(crop.read_bytes()).hexdigest()
        self.save()
        backend=FakeBackend()
        with patch.object(backend,"recognize",side_effect=[dict(text="OK",words=[]),RuntimeError("failure")]):
            self.assertEqual(ocr.recognize_bundle(self.path,backend=backend)["status"],"partial")


class CLITests(unittest.TestCase):
    def setUp(self):
        temp=tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root=Path(temp.name)
        self.path,_=bundle(self.root)
        self.output=self.root/"ocr.json"
        self.args=["--manifest",str(self.path),"--output",str(self.output),"--mode","both"]

    def run_cli(self,args):
        with contextlib.redirect_stdout(io.StringIO()),contextlib.redirect_stderr(io.StringIO()):
            return ocr.main(args)

    def test_success_output_overwrite_and_input_protection(self):
        with patch.object(ocr,"TesseractBackend",return_value=FakeBackend()):
            self.assertEqual(self.run_cli(self.args),0)
            before=self.output.read_bytes()
            self.assertEqual(self.run_cli(self.args),1)
            self.assertEqual(self.run_cli(self.args+["--overwrite"]),0)
            self.assertEqual(before,self.output.read_bytes())
            self.assertEqual(self.run_cli(["--manifest",str(self.path),"--output",str(self.path),"--overwrite"]),1)
            self.assertEqual(self.run_cli(["--manifest",str(self.path),"--output",str(self.root/"frame.png"),"--overwrite"]),1)

    def test_unavailable_output_and_exit_code(self):
        with patch.object(ocr.shutil,"which",return_value=None):
            self.assertEqual(self.run_cli(self.args),1)
            self.assertEqual(self.run_cli(["--check-backend"]),1)
        result=json.loads(self.output.read_text())
        self.assertEqual(result["status"],"unavailable")
        self.assertEqual(result["counts"]["text_found"],0)

    def test_atomic_failure(self):
        with patch.object(ocr,"TesseractBackend",return_value=FakeBackend()),patch(
                "timeline_query.os.link",side_effect=OSError("publication failure")):
            self.assertEqual(self.run_cli(self.args),1)
        self.assertFalse(self.output.exists())
        self.assertFalse(list(self.root.glob(".query-*")))

    def test_import_safety(self):
        script="""import sys
def audit(event,args):
    if event in ('subprocess.Popen','os.mkdir','os.remove'):
        raise AssertionError(event)
    if event=='open' and ((isinstance(args[1],str) and any(c in args[1] for c in 'wax+')) or args[2] & 3):
        raise AssertionError('write')
sys.addaudithook(audit)
import ocr_visual_evidence
assert not any(m in sys.modules for m in ('torch','pytesseract','easyocr','PIL'))
"""
        result=subprocess.run([sys.executable,"-B","-c",script],cwd=Path(ocr.__file__).parent,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout+result.stderr,"")


if __name__=="__main__":
    unittest.main()
