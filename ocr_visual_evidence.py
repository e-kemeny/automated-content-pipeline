"""Read-only OCR over verified visual-evidence images; no event classification."""
import argparse
from copy import deepcopy
import csv
from fractions import Fraction
import io
import json
from pathlib import Path, PurePosixPath, PureWindowsPath
import re
import shutil
import subprocess
import sys

from source_identity import file_identity, validate_identity
from multimodal_timeline import json_value, number, read_json
from visual_evidence import TIME_BASIS, configuration, crop_geometry, png_dimensions, validate_profile
from highlight_evaluation import digest, publish


def safe_image(root, name):
    if (not isinstance(name,str) or not name or "\\" in name or ":" in name
            or PureWindowsPath(name).anchor or PurePosixPath(name).is_absolute()
            or any(part in ("",".","..") for part in name.split("/"))):
        raise ValueError("Image path must be a confined relative path")
    path = root
    for part in name.split("/"):
        path = path/part
        if path.is_symlink() or getattr(path,"is_junction",lambda:False)():
            raise ValueError("Symlink/junction image paths are unsupported")
    if not path.resolve().is_relative_to(root) or not path.is_file():
        raise ValueError("Missing image or path outside artifact root")
    return path


def image_snapshot(path):
    stat = path.stat()
    sha,size = file_identity(path)
    return sha,size,stat.st_mtime_ns,stat.st_ctime_ns


def load_bundle(path):
    """Validate producer metadata and all referenced images before any OCR."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("Manifest symlinks are unsupported")
    initial = image_snapshot(path)
    manifest = read_json(path)
    root = path.resolve().parent
    snapshots = {path.resolve():initial}
    assets = []
    try:
        json_value(manifest)
        if (type(manifest["schema_version"]) is not int or manifest["schema_version"]!=1
                or manifest["artifact_type"]!="visual-evidence"):
            raise ValueError("Unsupported visual evidence schema")
        identity = validate_identity(manifest["source_identity"])
        duration = number(manifest["video_duration_seconds"])
        if duration!=identity["media"]["duration_seconds"]:
            raise ValueError("Source duration disagrees with identity")
        profile = validate_profile(manifest["profile"])
        config = manifest["sampling"]
        expected = configuration(duration,config["interval_seconds"],config["start_seconds"],
                                 config["end_seconds"],config["max_frames"],config["width"],config["height"])
        if config!=expected or manifest["extraction_provenance"]["time_basis"]!=TIME_BASIS:
            raise ValueError("Unsupported sampling or timestamp contract")
        if type(manifest["crops_enabled"]) is not bool or not isinstance(manifest["frames"],list):
            raise ValueError("Invalid frames/crops declaration")
        if len(manifest["frames"])>config["max_frames"] or manifest["coverage"]["frame_count"]!=len(manifest["frames"]):
            raise ValueError("Frame count disagrees with coverage")
        regions = {r["name"]:r for r in profile["regions"]}
        previous = -1
        ids = set()
        for frame in manifest["frames"]:
            pts,base = frame["normalized_pts"],frame["time_base"]
            if type(pts) is not int or pts<0 or not isinstance(base,str) or not re.fullmatch(r"\d+(?:/\d+)?",base):
                raise ValueError("Invalid measured PTS")
            time_base = Fraction(base)
            timestamp = number(frame["timestamp_seconds"])
            if (time_base<=0 or timestamp!=float(pts*time_base) or not previous<timestamp
                    or not config["start_seconds"]<=timestamp<config["end_seconds"]):
                raise ValueError("Invalid frame timestamp/order")
            previous = timestamp
            if (frame["width"],frame["height"])!=(config["width"],config["height"]):
                raise ValueError("Frame dimensions disagree with sampling")
            timing = {k:frame[k] for k in ("normalized_pts","time_base","timestamp_seconds")}
            expected_id = digest(dict(source=identity,timing=timing,width=frame["width"],height=frame["height"]))
            if frame["frame_id"]!=expected_id or expected_id in ids:
                raise ValueError("Invalid or duplicate frame identity")
            ids.add(expected_id)
            crops = frame["regions"]
            expected_names = list(regions) if manifest["crops_enabled"] else []
            if not isinstance(crops,list) or [c["region_name"] for c in crops]!=expected_names:
                raise ValueError("Crop list disagrees with extraction profile")
            for kind,item in [("full",frame)]+[("crop",crop) for crop in crops]:
                if kind=="crop":
                    region = regions[item["region_name"]]
                    rectangle = crop_geometry(region,frame["width"],frame["height"])
                    if (item["parent_frame_id"]!=expected_id or item["normalized_region"]!=region
                            or item["pixel_rectangle"]!=rectangle
                            or (item["width"],item["height"])!=(rectangle["width"],rectangle["height"])):
                        raise ValueError("Crop geometry or parent mismatch")
                if any(type(item[k]) is not int or item[k]<=0 for k in ("width","height")):
                    raise ValueError("Image dimensions must be positive integers")
                image = safe_image(root,item["image_path"])
                snapshot = image_snapshot(image)
                if snapshot[0]!=item["sha256"]:
                    raise ValueError("Image SHA-256 mismatch")
                if png_dimensions(image)!=(item["width"],item["height"]):
                    raise ValueError("Image dimensions mismatch")
                if image in snapshots and snapshots[image]!=snapshot:
                    raise ValueError("Image changed during validation")
                snapshots[image] = snapshot
                assets.append(dict(kind=kind,frame=frame,image=item,path=image))
    except (KeyError,TypeError,AttributeError,ZeroDivisionError) as exc:
        raise ValueError("Malformed visual evidence manifest") from exc
    return manifest,assets,snapshots


def settings_for(profile, language=None, psm=None):
    hints = profile["ui_hints"].get("ocr",{})
    if not isinstance(hints,dict) or hints.keys()-{"language","psm","preferred_regions"}:
        raise ValueError("Unsupported OCR profile hints")
    language = language if language is not None else hints.get("language","eng")
    psm = psm if psm is not None else hints.get("psm",3)
    if not isinstance(language,str) or not re.fullmatch(r"[A-Za-z0-9_]+(?:\+[A-Za-z0-9_]+)*",language):
        raise ValueError("Invalid OCR language identifier")
    if type(psm) is not int or not 3<=psm<=13:
        raise ValueError("OCR psm must be an integer from 3 to 13")
    preferred = hints.get("preferred_regions")
    if preferred is not None and (not isinstance(preferred,list) or any(not isinstance(n,str) for n in preferred)
            or len(set(preferred))!=len(preferred) or set(preferred)-{r["name"] for r in profile["regions"]}):
        raise ValueError("Preferred regions must name unique configured regions")
    return dict(language=language,psm=psm,preferred_regions=deepcopy(preferred))


def validate_result(result,width,height):
    json_value(result)
    if not isinstance(result,dict) or set(result)!={"text","words"} or not isinstance(result["text"],str) or not isinstance(result["words"],list):
        raise ValueError("Backend must return text and words")
    for word in result["words"]:
        if not isinstance(word,dict) or not isinstance(word.get("text"),str) or not word["text"].strip() or word.keys()-{"text","bbox","confidence"}:
            raise ValueError("Invalid OCR word")
        if "confidence" in word and not 0<=number(word["confidence"])<=100:
            raise ValueError("Invalid engine confidence")
        if "bbox" in word:
            box = word["bbox"]
            if not isinstance(box,dict) or set(box)!={"x","y","width","height"} or any(type(v) is not int for v in box.values()):
                raise ValueError("Invalid OCR bounding box")
            if not (box["x"]>=0 and box["y"]>=0 and box["width"]>0 and box["height"]>0
                    and box["x"]+box["width"]<=width and box["y"]+box["height"]<=height):
                raise ValueError("OCR bounding box outside input image")
    if result["words"] and not result["text"].strip():
        raise ValueError("Words disagree with empty text")
    return deepcopy(result)


def parse_tsv(text):
    reader = csv.DictReader(io.StringIO(text),delimiter="\t",quoting=csv.QUOTE_NONE)
    required = {"level","page_num","block_num","par_num","line_num","word_num","left","top","width","height","conf","text"}
    if reader.fieldnames is None or set(reader.fieldnames)!=required or len(reader.fieldnames)!=len(required):
        raise ValueError("Invalid Tesseract TSV header")
    words,lines = [],[]
    previous = None
    for row in reader:
        if None in row or any(v is None for v in row.values()):
            raise ValueError("Malformed Tesseract TSV row")
        level = int(row["level"])
        if not 1<=level<=5:
            raise ValueError("Unsupported Tesseract TSV hierarchy level")
        if level!=5 or not row["text"].strip():
            continue
        confidence = number(float(row["conf"]))
        if confidence!=-1 and not 0<=confidence<=100:
            raise ValueError("Invalid Tesseract confidence")
        word = dict(text=row["text"],bbox={new:int(row[old]) for new,old in
                    (("x","left"),("y","top"),("width","width"),("height","height"))})
        if confidence!=-1:
            word["confidence"] = confidence
        words.append(word)
        line = tuple(row[k] for k in ("page_num","block_num","par_num","line_num"))
        if line!=previous:
            lines.append([])
        lines[-1].append(row["text"])
        previous = line
    return dict(text="\n".join(" ".join(line) for line in lines),words=words)


class TesseractBackend:
    """Small injectable interface: check(language) and recognize(path,language,psm)."""
    identifier = "tesseract"

    def __init__(self, executable=None):
        self.requested = str(executable) if executable is not None else "tesseract"
        self.executable = None

    def check(self,language):
        self.executable = shutil.which(self.requested)
        info = dict(identifier=self.identifier,version=None,status="unavailable",reason=None,
                    executable=self.executable,confidence_scale="Tesseract word confidence 0-100; not calibrated probability")
        if self.executable is None:
            info["reason"] = "Tesseract executable not found; nothing installed or downloaded"
            return info
        try:
            version = subprocess.run([self.executable,"--version"],check=True,capture_output=True,text=True,timeout=10).stdout.splitlines()
            if not version or not version[0].lower().startswith("tesseract "):
                raise ValueError("Unrecognized Tesseract version output")
            info["version"] = version[0]
            available = subprocess.run([self.executable,"--list-langs"],check=True,capture_output=True,text=True,timeout=10).stdout.splitlines()
            languages = {line.strip() for line in available if re.fullmatch(r"[A-Za-z0-9_]+",line.strip())}
            info["installed_languages"] = sorted(languages)
            if set(language.split("+"))-languages:
                info["reason"] = "Requested language data unavailable; no downloads attempted"
            else:
                info.update(status="available",reason=None)
        except (OSError,ValueError,subprocess.SubprocessError) as exc:
            info.update(status="failed",reason=str(exc))
        return info

    def recognize(self,path,language,psm):
        if self.executable is None:
            raise RuntimeError("Backend availability must be checked before recognition")
        result = subprocess.run([self.executable,str(path),"-","-l",language,"--psm",str(psm),"tsv"],
            check=True,capture_output=True,text=True,encoding="utf-8",timeout=60)
        return parse_tsv(result.stdout)


def recognize_bundle(manifest_path, *, mode="both", backend=None, language=None, psm=None):
    if mode not in ("full","crops","both"):
        raise ValueError("Unknown OCR mode")
    manifest,assets,snapshots = load_bundle(manifest_path)
    settings = settings_for(manifest["profile"],language,psm)
    selected = [a for a in assets if (a["kind"]=="full" and mode in ("full","both")) or (
        a["kind"]=="crop" and mode in ("crops","both") and
        (settings["preferred_regions"] is None or a["image"]["region_name"] in settings["preferred_regions"]))]
    backend = backend if backend is not None else TesseractBackend()
    try:
        info = backend.check(settings["language"])
    except Exception as exc:
        info = dict(identifier=backend.identifier,version=None,status="failed",reason=f"{type(exc).__name__}: {exc}")
    json_value(info)
    if (not isinstance(info,dict) or info.get("status") not in ("available","unavailable","failed")
            or not isinstance(info.get("identifier"),str) or not info["identifier"]
            or info.get("version") is not None and not isinstance(info["version"],str)
            or info["status"]=="available" and not info.get("version")):
        raise ValueError("Invalid backend availability metadata")
    cache,observations = {},[]
    manifest_sha = snapshots[Path(manifest_path).resolve()][0]
    for asset in selected:
        frame,item,path = asset["frame"],asset["image"],asset["path"]
        region = item.get("region_name") if asset["kind"]=="crop" else None
        observation_id = digest(dict(manifest=manifest_sha,frame=frame["frame_id"],kind=asset["kind"],region=region))
        key = (item["sha256"],item["width"],item["height"],settings["language"],settings["psm"])
        reused = None
        if key in cache:
            reused,outcome = cache[key]
            outcome = deepcopy(outcome)
        else:
            if info["status"]!="available":
                outcome = dict(status="unavailable" if info["status"]=="unavailable" else "failed",
                               text=None,words=None,error=info.get("reason"))
            else:
                try:
                    result = validate_result(backend.recognize(path,settings["language"],settings["psm"]),item["width"],item["height"])
                    outcome = dict(result,status="text_found" if result["text"].strip() else "no_text",error=None)
                except Exception as exc:  # Adapter boundary; malformed output is a failure, never empty success.
                    outcome = dict(status="failed",text=None,words=None,error=f"{type(exc).__name__}: {exc}")
            cache[key] = observation_id,deepcopy(outcome)
        observations.append(dict(observation_id=observation_id,parent_frame_id=frame["frame_id"],kind=asset["kind"],
            region_name=region,image=deepcopy({k:v for k,v in item.items() if k!="regions"}),
            timestamp={k:frame[k] for k in ("normalized_pts","time_base","timestamp_seconds")},
            bbox_coordinate_system="input image pixels; crop boxes are not parent-frame coordinates",
            reused_from=reused,**outcome))
    for path,before in snapshots.items():
        if image_snapshot(path)!=before:
            raise ValueError("Input manifest or image changed during OCR")
    counts = {status:sum(o["status"]==status for o in observations) for status in ("text_found","no_text","unavailable","failed")}
    successes = counts["text_found"]+counts["no_text"]
    status = ("no_inputs" if not observations else "completed" if successes==len(observations) else
              "partial" if successes else "unavailable" if counts["unavailable"] else "failed")
    return dict(schema_version=1,artifact_type="ocr-visual-evidence",status=status,backend=info,
        source_identity=deepcopy(manifest["source_identity"]),source_identity_status="preserved_manifest_claim; source video not rehashed",
        visual_evidence_provenance=dict(manifest_sha256=manifest_sha,manifest=deepcopy(manifest)),
        mode=mode,settings=settings,observations=observations,counts=counts,
        coverage=dict(selected_images=len(selected),available_frames=len(manifest["frames"]),
            available_crops=sum(len(f["regions"]) for f in manifest["frames"]),unique_recognition_inputs=len(cache),
            no_inputs_reason="No extracted crops or no preferred regions selected" if not selected and mode=="crops" else None,
            semantic_coverage="unknown"),
        limitations=["OCR text is an observation, not a confirmed gameplay event.",
            "Measured frame timestamps retain the extractor's first-decoded-frame origin; event timing is unknown.",
            "Sparse samples and failed/unavailable OCR are not evidence that text or gameplay events were absent.",
            "Identical image bytes/settings reuse one result without discarding parent/crop relationships.",
            "No hostile concurrent filesystem mutation or arbitrary executable safety guarantee.",
            "Word confidence is engine-reported, not a calibrated probability or highlight score."])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--manifest",type=Path)
    parser.add_argument("--output",type=Path)
    parser.add_argument("--backend",choices=("tesseract",),default="tesseract")
    parser.add_argument("--executable")
    parser.add_argument("--mode",choices=("full","crops","both"),default="both")
    parser.add_argument("--language")
    parser.add_argument("--psm",type=int)
    parser.add_argument("--check-backend",action="store_true")
    parser.add_argument("--overwrite",action="store_true")
    args = parser.parse_args(argv)
    backend = TesseractBackend(args.executable)
    if args.check_backend and (args.manifest is not None or args.output is not None or args.overwrite):
        parser.error("--check-backend cannot be combined with manifest/output/overwrite")
    if not args.check_backend and (args.manifest is None or args.output is None):
        parser.error("--manifest and --output are required for OCR")
    try:
        if args.check_backend:
            settings = settings_for({"ui_hints":{},"regions":[]},args.language,args.psm)
            result = backend.check(settings["language"])
            print(json.dumps(result,sort_keys=True,indent=2))
            return 0 if result["status"]=="available" else 1
        if args.output.exists() and not args.overwrite:
            raise FileExistsError("Output exists; explicit --overwrite required")
        result = recognize_bundle(args.manifest,mode=args.mode,backend=backend,language=args.language,psm=args.psm)
        manifest = result["visual_evidence_provenance"]["manifest"]
        root = args.manifest.resolve().parent
        inputs = [args.manifest]+[safe_image(root,item["image_path"]) for frame in manifest["frames"]
                                for item in [frame]+frame["regions"]]
        publish(result,args.output,inputs,args.overwrite)
        print(f"Saved {args.output}: {result['status']}; {result['counts']}")
        return 0 if result["status"] in ("completed","no_inputs") else 1
    except (OSError,ValueError) as exc:
        print(f"FAIL: OCR visual evidence: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
