"""CPU frame evidence with measured normalized PTS; no OCR or classification."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import re
import struct
import subprocess
import sys
import tempfile

from vision_inference import inspect_video
from source_identity import canonical, file_identity, validate_identity
from multimodal_timeline import json_value, number, read_json

ROOT = Path(__file__).resolve().parent
TIME_BASIS = "decoded video PTS minus first decoded video PTS; not requested seek times"
LIMITATIONS = [
    "Sparse visual evidence only: no OCR, game identification or gameplay-event recognition.",
    "Timestamps use the first decoded video frame as zero; container/audio origins are not reconstructed.",
    "Actual PTS and time base are retained; timestamp_seconds is their floating-point representation.",
    "Sampling selects the first eligible frame, then frames at least interval seconds apart; not an exact grid.",
    "Frames between samples, beyond the cap or outside the range are not represented; semantic coverage is unknown.",
    "Images are resized to the requested dimensions; a different aspect ratio stretches the image.",
    "Regions and UI hints are illustrative configuration, not verified text locations.",
    "No concurrent writers or hostile filesystem mutation are supported.",
]


def validate_profile(profile):
    try:
        json_value(profile)
        if (set(profile) != {"schema_version","profile_version","game_id","regions","ui_hints"}
                or type(profile["schema_version"]) is not int or profile["schema_version"] != 1
                or type(profile["profile_version"]) is not int or profile["profile_version"] != 1):
            raise ValueError("Unsupported visual profile schema/version")
        if not isinstance(profile["game_id"],str) or not profile["game_id"].strip():
            raise ValueError("Profile requires game_id")
        if not isinstance(profile["ui_hints"],dict):
            raise ValueError("UI hints must be an object")
        if not isinstance(profile["regions"],list) or not 1 <= len(profile["regions"]) <= 16:
            raise ValueError("Profile requires 1 to 16 regions")
        names = set()
        for region in profile["regions"]:
            if set(region) != {"name","x","y","width","height"}:
                raise ValueError("Invalid region fields")
            name = region["name"]
            if not isinstance(name,str) or not re.fullmatch(r"[a-z][a-z0-9_]{0,47}",name) or name in names:
                raise ValueError("Region names must be unique safe lowercase identifiers")
            names.add(name)
            x,y,w,h = (number(region[k]) for k in ("x","y","width","height"))
            if not (0 <= x <= 1 and 0 <= y <= 1 and 0 < w <= 1 and 0 < h <= 1
                    and x+w <= 1 and y+h <= 1):
                raise ValueError("Region rectangle must be positive and inside normalized frame")
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed visual profile") from exc
    return deepcopy(profile)


def load_profile(game=None, profile_path=None):
    if game is not None and profile_path is not None:
        raise ValueError("Use --game or --profile, not both")
    if profile_path is not None:
        return validate_profile(read_json(profile_path)), False
    known = {"generic":"visual_generic_v1.json", "bedwars":"visual_bedwars_v1.json"}
    requested = game or "generic"
    return validate_profile(read_json(ROOT/"profiles"/known.get(requested,known["generic"]))), requested not in known


def configuration(duration, interval=2, start=0, end=None, max_frames=120, width=640, height=360):
    duration,interval,start = number(duration),number(interval),number(start)
    end = duration if end is None else number(end)
    if duration <= 0 or interval <= 0 or not 0 <= start <= end <= duration:
        raise ValueError("Positive duration/interval and 0 <= start <= end <= duration required")
    for value,limit,label in ((max_frames,1000,"max_frames"),(width,4096,"width"),(height,4096,"height")):
        if type(value) is not int or not 1 <= value <= limit:
            raise ValueError(f"{label} must be an integer from 1 to {limit}")
    return dict(interval_seconds=interval,start_seconds=start,end_seconds=end,
                max_frames=max_frames,width=width,height=height)


def crop_geometry(region, width, height):
    # Floor origin and ceil far edge preserve the requested area after pixel rounding.
    x = math.floor(region["x"]*width)
    y = math.floor(region["y"]*height)
    right = min(width,math.ceil((region["x"]+region["width"])*width))
    bottom = min(height,math.ceil((region["y"]+region["height"])*height))
    return dict(x=x,y=y,width=right-x,height=bottom-y)


def png_dimensions(path):
    with Path(path).open("rb") as handle:
        header = handle.read(24)
    if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n" or header[12:16] != b"IHDR":
        raise ValueError("Missing or invalid extracted PNG")
    width,height = struct.unpack(">II",header[16:24])
    if not width or not height:
        raise ValueError("Invalid PNG dimensions")
    return width,height


def parse_timestamps(log):
    time_base = None
    rows = []
    with Path(log).open(encoding="utf-8",errors="replace") as handle:
        for line in handle:
            if "showinfo" not in line:
                continue
            base = re.search(r"config in time_base:\s*(\d+)/(\d+)",line)
            if base:
                if int(base[2]) == 0:
                    raise ValueError("Zero FFmpeg time-base denominator")
                value = Fraction(int(base[1]),int(base[2]))
                if value <= 0 or time_base is not None and value != time_base:
                    raise ValueError("Invalid or changing decoded time base")
                time_base = value
            frame = re.search(r"\bn:\s*(\d+)\s+pts:\s*(-?\d+)\s+pts_time:",line)
            if frame:
                if time_base is None or int(frame[1]) != len(rows):
                    raise ValueError("Missing time base or nonsequential FFmpeg frames")
                pts = int(frame[2])
                exact = pts*time_base
                if exact < 0 or rows and exact <= Fraction(rows[-1]["normalized_pts"])*time_base:
                    raise ValueError("Non-increasing decoded timestamps")
                rows.append(dict(normalized_pts=pts,time_base=str(time_base),timestamp_seconds=float(exact)))
    return rows


def extract_frames(video, stream_index, stage, config):
    filters = (
        "setpts=PTS-STARTPTS,"
        f"select='gte(t,{config['start_seconds']})*lt(t,{config['end_seconds']})*"
        f"(isnan(prev_selected_t)+gte(t-prev_selected_t,{config['interval_seconds']}))',"
        f"trim=end_frame={config['max_frames']},"
        f"scale={config['width']}:{config['height']},setsar=1,showinfo"
    )
    command = ["ffmpeg","-hide_banner","-v","info","-nostdin","-n","-copyts","-i",str(video),
        "-map",f"0:{stream_index}","-an","-sn","-vf",filters,"-fps_mode","passthrough",
        "-frames:v",str(config["max_frames"]),"-pix_fmt","rgb24",str(stage/"sample_%06d.png")]
    log = stage/"extraction.log"
    with log.open("w",encoding="utf-8",newline="\n") as handle:
        subprocess.run(command,check=True,stdout=subprocess.DEVNULL,stderr=handle,timeout=600)
    return parse_timestamps(log), filters


def extract_crop(frame, target, rectangle):
    x,y,w,h = (rectangle[k] for k in ("x","y","width","height"))
    subprocess.run(["ffmpeg","-v","error","-nostdin","-n","-i",str(frame),
        "-vf",f"crop={w}:{h}:{x}:{y}","-frames:v","1","-pix_fmt","rgb24",str(target)],
        check=True,capture_output=True,text=True,timeout=60)


def extract_evidence(video, output_root, *, interval=2, start=0, end=None, max_frames=120,
                     width=640, height=360, game=None, profile_path=None, crops=False, expected_identity=None):
    video, destination = Path(video),Path(output_root)
    if destination.exists() or destination.is_symlink():
        raise FileExistsError("Visual evidence requires a new output directory; no overwrite or repair")
    resolved = destination.resolve()
    if resolved.is_relative_to(ROOT):
        parts = resolved.relative_to(ROOT).parts
        if len(parts)<2 or parts[0]!="output" or not parts[1].startswith("visual_evidence"):
            raise ValueError("Repository extraction must be isolated under output/visual_evidence*")
    profile,fallback = load_profile(game,profile_path)
    initial_stat = video.stat()
    media = inspect_video(video)  # Existing FFprobe/video validation, no model imports.
    config = configuration(media["duration_seconds"],interval,start,end,max_frames,width,height)
    before = file_identity(video)
    identity = validate_identity(dict(version=1,algorithm="sha256",digest=before[0],size_bytes=before[1],
        media={key:media[key] for key in ("duration_seconds","width","height")}))
    if expected_identity is not None and validate_identity(expected_identity) != identity:
        raise ValueError("Conflicting expected source content identity")
    version_lines = subprocess.run(["ffmpeg","-version"],check=True,capture_output=True,text=True,timeout=10).stdout.splitlines()
    if not version_lines:
        raise ValueError("Missing FFmpeg version output")
    version = version_lines[0]
    manifest = dict(schema_version=1,artifact_type="visual-evidence",source_identity=identity,
        source_location=str(video.resolve()),video_duration_seconds=media["duration_seconds"],sampling=config,
        profile=profile,requested_game=game,unknown_game_fallback=fallback,crops_enabled=crops,frames=[],
        extraction_provenance=dict(ffmpeg_version=version,stream_index=media["stream_index"],time_basis=TIME_BASIS),
        limitations=list(LIMITATIONS))
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".visual-evidence-",dir=destination.parent) as temporary:
        stage = Path(temporary)
        timestamps, filters = ([],None) if start==config["end_seconds"] else extract_frames(video,media["stream_index"],stage,config)
        images = sorted(stage.glob("sample_*.png"))
        if len(images)!=len(timestamps) or len(images)>max_frames:
            raise ValueError("Frame images and measured timestamps disagree")
        for index,(image,timing) in enumerate(zip(images,timestamps)):
            t = timing["timestamp_seconds"]
            if not config["start_seconds"] <= t < config["end_seconds"]:
                raise ValueError("Decoded frame outside requested range")
            if png_dimensions(image)!=(width,height):
                raise ValueError("Unexpected frame dimensions")
            frame_id = hashlib.sha256(canonical(dict(source=identity,timing=timing,width=width,height=height))).hexdigest()
            filename = f"frame_{index:06d}_{frame_id[:20]}.png"
            target = stage/filename
            image.rename(target)
            row = dict(frame_id=frame_id,**timing,image_path=filename,width=width,height=height,
                       sha256=file_identity(target)[0],regions=[])
            if crops:
                for region in profile["regions"]:
                    rectangle = crop_geometry(region,width,height)
                    name = f"frame_{index:06d}_{frame_id[:20]}__{region['name']}.png"
                    crop = stage/name
                    extract_crop(target,crop,rectangle)
                    if png_dimensions(crop)!=(rectangle["width"],rectangle["height"]):
                        raise ValueError("Unexpected crop dimensions")
                    row["regions"].append(dict(parent_frame_id=frame_id,region_name=region["name"],
                        image_path=name,normalized_region=deepcopy(region),pixel_rectangle=rectangle,
                        width=rectangle["width"],height=rectangle["height"],sha256=file_identity(crop)[0]))
            manifest["frames"].append(row)
        final_stat = video.stat()
        if file_identity(video)!=before or any(getattr(initial_stat,k)!=getattr(final_stat,k)
                for k in ("st_dev","st_ino","st_size","st_mtime_ns","st_ctime_ns")):
            raise ValueError("Source content changed during extraction")
        manifest["extraction_provenance"]["filter"] = filters
        log = stage/"extraction.log"
        manifest["extraction_provenance"]["log"] = dict(path=log.name,sha256=file_identity(log)[0]) if log.exists() else None
        manifest["coverage"] = dict(frame_count=len(images),status="sampled" if images else "no_frames",
            max_frame_limit_reached=len(images)==max_frames,temporal_coverage="sparse; unknown between samples")
        (stage/"visual_evidence_manifest.json").write_text(
            json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False)+"\n",encoding="utf-8",newline="\n")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Destination appeared during extraction")
        os.rename(stage,destination)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--video",type=Path,required=True)
    parser.add_argument("--output-root",type=Path,default=Path("output/visual_evidence_v1"))
    parser.add_argument("--interval",type=float,default=2)
    parser.add_argument("--start",type=float,default=0)
    parser.add_argument("--end",type=float)
    parser.add_argument("--max-frames",type=int,default=120)
    parser.add_argument("--width",type=int,default=640)
    parser.add_argument("--height",type=int,default=360)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--game")
    group.add_argument("--profile",dest="profile_path",type=Path)
    parser.add_argument("--crops",action="store_true")
    parser.add_argument("--expected-identity",type=Path,help="Optional source_identity.py identity JSON")
    args = vars(parser.parse_args(argv))
    try:
        if args["expected_identity"] is not None:
            args["expected_identity"] = read_json(args["expected_identity"])
        result = extract_evidence(**args)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(f"FAIL: visual evidence: {exc}",file=sys.stderr)
        return 1
    print(f"Saved {len(result['frames'])} sampled frames to {args['output_root']}; no OCR or classification")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
