"""Export persisted candidates only; no detector/model inference or shared-analysis writes."""
import argparse
from copy import deepcopy
from fractions import Fraction
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from evaluation import select_highlights
from shared_analysis import load_analysis
from transcription import media_sha256, probe_media, require_media
from windows import build_candidate_windows

EXPORTER = "shorts-export-v1"


def select_windows(analysis, top_k):
    if type(top_k) is not int or top_k <= 0:
        raise ValueError("top-k must be a positive integer")
    envelope = analysis["candidate_windows"]
    rows, provenance = envelope["data"], envelope["provenance"]
    if envelope["status"] != "analyzed" or not rows:
        raise ValueError("Missing persisted candidate evidence; detectors will not run")
    detector = provenance.get("detector")
    score_key = {"Audio-only": "score", "Audio + Scene": "highlight_score"}.get(detector)
    if score_key is None or provenance.get("variant") != "fixed":
        raise ValueError("Require explicit Audio-only/Audio + Scene fixed candidate provenance")
    for row in rows:
        if "second" not in row or isinstance(row["second"], bool) or not isinstance(row["second"], (int, float)) or not math.isfinite(row["second"]):
            raise ValueError("Missing numeric candidate timestamp")
        if score_key in row and (isinstance(row[score_key], bool) or
                not isinstance(row[score_key], (int, float)) or not math.isfinite(row[score_key])):
            raise ValueError("Invalid original ranking score")
    kind = provenance.get("representation", "selected_windows")
    if kind == "candidate_pool":
        if detector != "Audio + Scene" or any(score_key not in row for row in rows):
            raise ValueError("Candidate pools require original Audio + Scene highlight_score")
        # Stable tie order must be explicitly preserved despite chronological schema ordering.
        if any(type(row.get("ranking_order")) is not int for row in rows):
            raise ValueError("Complete pools require original ranking_order for stable score ties")
        order = [row["ranking_order"] for row in rows]
        if len(set(order)) != len(order) or min(order) < 0:
            raise ValueError("Invalid original ranking_order")
        selected = select_highlights(sorted(rows, key=lambda r: r["ranking_order"]),
                                     score_key, limit=top_k)
        if len(selected) < top_k:
            raise ValueError("Persisted pool cannot supply requested top-k after suppression")
        mode = "ranked_persisted_pool"
    elif kind == "selected_windows":
        if provenance.get("k") != len(rows) or top_k != len(rows):
            raise ValueError(f"Only {len(rows)} persisted selected windows available; top-k must equal that selection")
        if any(abs(a["second"]-b["second"]) < 15 for i,a in enumerate(rows) for b in rows[i+1:]):
            raise ValueError("Persisted selection violates frozen 15-second separation")
        selected, mode = rows, "reused_persisted_selection"
    else:
        raise ValueError("Unknown candidate representation")
    return build_candidate_windows(selected, analysis["source_video"]["duration_seconds"]), dict(
        mode=mode, detector=detector, ranking_score_key=score_key, top_k=top_k,
        separation_seconds=15, seconds_before=10, seconds_after=5,
        fresh_ranking=mode == "ranked_persisted_pool", provenance=deepcopy(provenance))


def probe_clip(path):
    result = subprocess.run(["ffprobe","-v","error","-show_format","-show_streams","-of","json",str(path)],
                            check=True,capture_output=True,text=True)
    data = json.loads(result.stdout)
    streams = data["streams"]
    duration = float(data["format"]["duration"])
    if not math.isfinite(duration) or duration <= 0 or not {"audio","video"} <= {s["codec_type"] for s in streams}:
        raise ValueError("Export lacks valid audio/video streams or duration")
    return dict(duration_seconds=duration, streams=[
        {k:s[k] for k in ("codec_type","codec_name","start_time","duration","avg_frame_rate") if k in s}
        for s in streams if s["codec_type"] in ("video","audio")])


def verify_duration(probe, requested_duration):
    # Frame and AAC packet precision are export verification limits, not detector tolerances.
    tolerance = 0.05
    for stream in probe["streams"]:
        if stream.get("codec_type") == "video":
            try:
                rate = Fraction(stream.get("avg_frame_rate", "0/1"))
            except (ValueError, ZeroDivisionError):
                continue
            if rate > 0:
                tolerance = max(tolerance, float(1/rate))
    error = probe["duration_seconds"]-requested_duration
    if abs(error) > tolerance:
        raise ValueError(f"Export duration error {error:.6f}s exceeds frame/packet precision {tolerance:.6f}s")
    return error


def plan_export(video, analysis_path, top_k=5, output_root=Path("output")):
    video = require_media(video)
    analysis_path = Path(analysis_path)
    analysis = load_analysis(analysis_path)
    actual = probe_media(video)  # FFprobe/hash only, never audio extraction or ASR.
    if "width" not in actual:
        raise ValueError("Source must contain both video and audio")
    source = analysis["source_video"]
    if not math.isclose(actual["duration_seconds"], source["duration_seconds"], rel_tol=0, abs_tol=1e-6):
        raise ValueError("Source duration differs from shared analysis")
    if not source.get("sha256"):
        raise ValueError("Persisted SHA-256 source identity required; do not guess from path/duration")
    if actual["sha256"] != source["sha256"]:
        raise ValueError("Source identity mismatch")
    windows, policy = select_windows(analysis, top_k)
    root = Path(output_root).resolve()
    directory = (root/video.stem/"shorts").resolve()
    if not directory.is_relative_to(root) or directory == root:
        raise ValueError("Unsafe output directory")
    entries = []
    for i, window in enumerate(windows,1):
        filename = f"clip_{i:02d}_t{window['second']:09.3f}.mp4"
        target = directory/filename
        if target.is_symlink() or target.resolve().parent != directory or target.resolve() in (video, analysis_path.resolve()):
            raise ValueError("Output must not overwrite source/analysis or follow a file symlink")
        entries.append(dict(candidate_timestamp=window["second"], start=window["start"], end=window["end"],
            duration=window["duration"], ranking_score=window.get(policy["ranking_score_key"]),
            ranking_score_key=policy["ranking_score_key"], candidate_evidence=deepcopy(window),
            output_filename=filename, status="planned", error=None))
    manifest = dict(manifest_version=1, exporter=EXPORTER, source=actual,
        shared_analysis=dict(path=str(analysis_path), schema_version=analysis["schema_version"],
            sha256=hashlib.sha256(analysis_path.read_bytes()).hexdigest()),
        selection=policy, encoding=dict(video="libx264",audio="aac",crf=18,preset="fast"),
        clips=entries)
    return video, directory, manifest


def previous_manifest(directory, manifest):
    path = directory/"shorts_manifest.json"
    if not path.exists():
        return {}
    if path.is_symlink():
        raise ValueError("Refusing symlink manifest")
    prior = json.loads(path.read_text(encoding="utf-8"))
    if prior.get("exporter") != EXPORTER or prior.get("manifest_version") != 1 or prior.get("source",{}).get("sha256") != manifest["source"]["sha256"]:
        raise ValueError("Existing manifest is unrelated; refusing replacement")
    if not isinstance(prior.get("clips"),list) or any(not isinstance(row,dict) or not isinstance(row.get("output_filename"),str) for row in prior["clips"]):
        raise ValueError("Invalid existing manifest clip records")
    return {row["output_filename"]:row for row in prior["clips"]}


def export_shorts(video, analysis_path, *, top_k=5, output_root=Path("output"), dry_run=False, force=False):
    video, directory, manifest = plan_export(video, analysis_path, top_k, output_root)
    if dry_run:
        return directory, manifest  # No mkdir, manifest write, clip write, or FFmpeg.
    manifest_path = directory/"shorts_manifest.json"
    original_manifest = manifest_path.read_bytes() if manifest_path.exists() else None
    previous = previous_manifest(directory, manifest)
    # Preflight every target before creating/replacing anything.
    for row in manifest["clips"]:
        target = directory/row["output_filename"]
        if target.exists():
            old = previous.get(row["output_filename"],{})
            if old.get("status") not in ("exported","reused","failed") or not old.get("output_sha256") or media_sha256(target) != old["output_sha256"]:
                raise ValueError(f"Existing file is unowned or changed; refusing overwrite: {target}")
            if any(old.get(k) != row[k] for k in ("candidate_timestamp","start","end","duration")):
                raise ValueError("Existing clip boundaries differ; refusing reuse")
    directory.mkdir(parents=True, exist_ok=True)
    for row in manifest["clips"]:
        target = directory/row["output_filename"]
        if target.exists() and not force:
            try:
                row["verification"] = probe_clip(target)
                row["duration_error_seconds"] = verify_duration(row["verification"],row["duration"])
                row["output_sha256"] = media_sha256(target)
                row["status"] = "reused"
            except (OSError,ValueError,subprocess.SubprocessError) as exc:
                row.update(status="failed",error=str(exc))
            continue
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(dir=directory,prefix=".shorts_",suffix=".mp4",delete=False) as handle:
                temporary = Path(handle.name)
            # Re-encode after accurate input seeking; both streams retain common timing.
            subprocess.run(["ffmpeg","-v","error","-nostdin","-y","-ss",str(row["start"]),
                "-i",str(video),"-t",str(row["duration"]),"-map","0:v:0","-map","0:a:0",
                "-c:v","libx264","-preset","fast","-crf","18","-pix_fmt","yuv420p",
                "-c:a","aac","-b:a","192k","-movflags","+faststart",str(temporary)],
                check=True,capture_output=True,text=True)
            row["verification"] = probe_clip(temporary)
            row["duration_error_seconds"] = verify_duration(row["verification"],row["duration"])
            row["output_sha256"] = media_sha256(temporary)
            # No-force publication is exclusive, even if a file appeared during encoding.
            if force and target.exists():
                if target.is_symlink() or media_sha256(target) != previous.get(row["output_filename"],{}).get("output_sha256"):
                    raise ValueError("Target changed during export")
                os.replace(temporary,target)
            else:
                os.link(temporary,target)  # Same directory/filesystem; fails if target already exists.
            row["status"] = "exported"
        except (OSError,ValueError,subprocess.SubprocessError) as exc:
            detail = getattr(exc,"stderr",None) or str(exc)
            row.update(status="failed",error=detail)
            old = previous.get(row["output_filename"],{})
            if target.exists() and old.get("output_sha256") and media_sha256(target) == old["output_sha256"]:
                row["output_sha256"] = old["output_sha256"]  # Preserve ownership of retained output after a failed forced refresh.
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
    with tempfile.NamedTemporaryFile(dir=directory,prefix=".manifest_",suffix=".json",delete=False) as handle:
        temporary = Path(handle.name)
    try:
        temporary.write_text(json.dumps(manifest,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
        if original_manifest is None:
            os.link(temporary,manifest_path)  # Never overwrite a concurrently created unrelated manifest.
        else:
            if manifest_path.is_symlink() or manifest_path.read_bytes() != original_manifest:
                raise ValueError("Manifest changed during export; refusing replacement")
            os.replace(temporary,manifest_path)
    finally:
        temporary.unlink(missing_ok=True)
    return directory, manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video",type=Path)
    parser.add_argument("--analysis",type=Path,required=True)
    parser.add_argument("--top-k",type=int,default=5)
    parser.add_argument("--output-root",type=Path,default=Path("output"))
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--force",action="store_true")
    args=parser.parse_args(argv)
    try:
        directory,manifest=export_shorts(args.video,args.analysis,top_k=args.top_k,
            output_root=args.output_root,dry_run=args.dry_run,force=args.force)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        parser.exit(1,f"Shorts export failed: {exc}\n")
    print(f"{manifest['selection']['mode']} ({manifest['selection']['detector']}); {directory}")
    for row in manifest["clips"]:
        print(f"{row['candidate_timestamp']}s: [{row['start']}, {row['end']}] "
              f"{row['status']} -> {directory/row['output_filename']}")
        if row["error"]:
            print(row["error"])
    return int(any(row["status"]=="failed" for row in manifest["clips"]))


if __name__=="__main__":
    raise SystemExit(main())
