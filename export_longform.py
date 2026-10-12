"""Baseline chronological assembly from persisted preselected anchors; no inference."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import tempfile

from export_shorts import plan_export as validate_source_selection, probe_clip, verify_duration
from shared_analysis import load_analysis
from transcription import media_sha256
from windows import build_candidate_windows

EXPORTER = "longform-export-v1"
ENCODING = dict(video="libx264", pixel_format="yuv420p", crf=18, preset="fast",
                intermediate_audio="pcm_s16le", sample_rate=48000, channels=2,
                final_audio="aac", audio_bitrate="192k", frame_mode="cfr")


def plan_segments(candidates, duration, seconds_before=15, seconds_after=15, merge_gap=5):
    """Expand all supplied anchors; merge touching/nearby windows including their gap."""
    for value in (seconds_before, seconds_after, merge_gap):
        if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or value < 0:
            raise ValueError("Context and merge gap must be finite nonnegative numbers")
    if not candidates:
        raise ValueError("No candidate anchors")
    expanded = build_candidate_windows(sorted(candidates,key=lambda r:r["second"]),duration,
                                       seconds_before,seconds_after)
    segments = []
    for window in expanded:
        if window["duration"] <= 0:
            raise ValueError("Context produces an empty segment")
        if segments and window["start"] <= segments[-1]["end"]+merge_gap:
            segments[-1]["end"] = max(segments[-1]["end"],window["end"])
            segments[-1]["anchors"].append(window["second"])
        else:
            segments.append(dict(start=window["start"],end=window["end"],anchors=[window["second"]]))
        segments[-1]["duration"] = segments[-1]["end"]-segments[-1]["start"]
    return expanded,segments


def signature(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False).encode()).hexdigest()


def prepare_plan(video, analysis_path, output_root=Path("output"), seconds_before=15, seconds_after=15, merge_gap=5):
    analysis_path=Path(analysis_path)
    original_analysis=analysis_path.read_bytes()
    analysis=load_analysis(analysis_path)
    envelope=analysis["candidate_windows"]
    if envelope["status"] != "analyzed" or not envelope["data"]:
        raise ValueError("Missing persisted candidate anchors; analysis will not run")
    if envelope["provenance"].get("representation","selected_windows") != "selected_windows":
        raise ValueError("Long-form V1 requires persisted preselected anchors, not a candidate pool")
    # Reuse source/schema/identity and frozen-selection validation, without calling Shorts export.
    video,_,short_plan=validate_source_selection(video,analysis_path,len(envelope["data"]),output_root)
    if analysis_path.read_bytes()!=original_analysis or short_plan["shared_analysis"]["sha256"]!=hashlib.sha256(original_analysis).hexdigest():
        raise ValueError("Analysis changed during planning")
    candidates=[row["candidate_evidence"] for row in short_plan["clips"]]
    expanded,segments=plan_segments(candidates,short_plan["source"]["duration_seconds"],
                                   seconds_before,seconds_after,merge_gap)
    root=Path(output_root).resolve()
    directory=(root/video.stem/"longform").resolve()
    if not directory.is_relative_to(root) or directory==root:
        raise ValueError("Unsafe output directory")
    for name in ("longform_v1.mp4","longform_manifest.json"):
        target=directory/name
        if target.is_symlink() or target.resolve().parent!=directory or target.resolve() in (video,analysis_path.resolve()):
            raise ValueError("Output must not overwrite input or follow a file symlink")
    planning=dict(status="planned",selection_mode="persisted_preselected_anchors",
        selection_provenance=deepcopy(envelope["provenance"]),
        candidate_anchors=[row["second"] for row in candidates],candidate_evidence=candidates,
        seconds_before=float(seconds_before),seconds_after=float(seconds_after),merge_gap=float(merge_gap),
        expanded_windows=expanded,source_intervals=deepcopy(segments),final_segment_count=len(segments),
        estimated_duration_seconds=sum(row["duration"] for row in segments))
    identity=dict(exporter=EXPORTER,source_sha256=short_plan["source"]["sha256"],
                  source_duration=short_plan["source"]["duration_seconds"],planning=planning,encoding=ENCODING)
    manifest=dict(manifest_version=1,exporter=EXPORTER,source=short_plan["source"],
        shared_analysis=short_plan["shared_analysis"],plan_signature=signature(identity),
        planning=planning,encoding=deepcopy(ENCODING),
        segments=[dict(row,status="planned",error=None) for row in segments],
        assembly=dict(status="planned",error=None,actual_duration_seconds=None,assembled_segment_count=0,
                      output_path=str(directory/"longform_v1.mp4")))
    return video,directory,manifest


def read_previous(path, manifest):
    if not path.exists():
        return None
    if path.is_symlink():
        raise ValueError("Refusing symlink manifest")
    prior=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(prior,dict) or prior.get("exporter")!=EXPORTER or prior.get("manifest_version")!=1 or not isinstance(prior.get("source"),dict) or prior["source"].get("sha256")!=manifest["source"]["sha256"] or not isinstance(prior.get("assembly"),dict):
        raise ValueError("Existing manifest is unrelated or invalid; refusing replacement")
    if not isinstance(prior.get("plan_signature"),str) or prior["assembly"].get("status") not in ("complete","reused","failed"):
        raise ValueError("Invalid existing assembly identity/status")
    return prior


def owned_hash(prior):
    if not prior:
        return None
    return prior["assembly"].get("output_sha256") or prior["assembly"].get("retained_previous_output",{}).get("sha256")


def save_manifest(manifest,path,original):
    with tempfile.NamedTemporaryFile(dir=path.parent,prefix=".longform_manifest_",suffix=".json",delete=False) as handle:
        temporary=Path(handle.name)
    try:
        temporary.write_text(json.dumps(manifest,indent=2,sort_keys=True,allow_nan=False)+"\n",encoding="utf-8")
        if original is None:
            os.link(temporary,path)
        else:
            if path.is_symlink() or path.read_bytes()!=original:
                raise ValueError("Manifest changed during assembly")
            os.replace(temporary,path)
    finally:
        temporary.unlink(missing_ok=True)


def export_longform(video,analysis_path,*,output_root=Path("output"),seconds_before=15,
                    seconds_after=15,merge_gap=5,dry_run=False,force=False):
    video,directory,manifest=prepare_plan(video,analysis_path,output_root,seconds_before,seconds_after,merge_gap)
    if dry_run:
        return directory,manifest
    output=directory/"longform_v1.mp4"
    manifest_path=directory/"longform_manifest.json"
    original=manifest_path.read_bytes() if manifest_path.exists() else None
    prior=read_previous(manifest_path,manifest)
    old_hash=owned_hash(prior)
    if output.exists():
        if not old_hash or media_sha256(output)!=old_hash:
            raise ValueError("Existing output is unowned or changed; refusing overwrite even with force")
        compatible=prior["plan_signature"]==manifest["plan_signature"] and prior["assembly"]["status"] in ("complete","reused")
        if not force:
            if not compatible:
                raise ValueError("Cached plan/config differs or previous assembly failed; use --force")
            verified=probe_clip(output)
            error=verify_duration(verified,manifest["planning"]["estimated_duration_seconds"])
            manifest["assembly"].update(status="reused",verification=verified,assembled_segment_count=len(manifest["segments"]),
                actual_duration_seconds=verified["duration_seconds"],duration_error_seconds=error,output_sha256=old_hash)
            for row in manifest["segments"]:
                row["status"]="reused_from_final"
            save_manifest(manifest,manifest_path,original)
            return directory,manifest
    directory.mkdir(parents=True,exist_ok=True)
    failed=False
    with tempfile.TemporaryDirectory(dir=directory,prefix=".longform_") as work:
        work=Path(work)
        files=[]
        for index,row in enumerate(manifest["segments"],1):
            if failed:
                row.update(status="skipped",error="Earlier segment export failed")
                continue
            path=work/f"segment_{index:02d}.mkv"
            try:
                fps=manifest["source"].get("fps")
                command=["ffmpeg","-v","error","-nostdin","-y","-ss",str(row["start"]),
                    "-i",str(video),"-t",str(row["duration"]),"-map","0:v:0","-map","0:a:0",
                    "-c:v","libx264","-preset","fast","-crf","18","-pix_fmt","yuv420p",
                    "-fps_mode","cfr"]
                if fps:
                    command+=["-r",str(fps)]
                command+=["-c:a","pcm_s16le","-ar","48000","-ac","2",str(path)]
                subprocess.run(command,check=True,capture_output=True,text=True)
                row["verification"]=probe_clip(path)
                row["duration_error_seconds"]=verify_duration(row["verification"],row["duration"])
                row.update(status="encoded_temporary",temporary_removed=True)
                files.append(path)
            except (OSError,ValueError,subprocess.SubprocessError) as exc:
                row.update(status="failed",error=getattr(exc,"stderr",None) or str(exc))
                manifest["assembly"].update(status="failed",error=f"Segment {index}: {row['error']}")
                failed=True
        if not failed:
            try:
                listing=work/"concat.txt"
                listing.write_text("".join(f"file '{path.name}'\n" for path in files),encoding="utf-8")
                combined=work/"assembled.mp4"
                subprocess.run(["ffmpeg","-v","error","-nostdin","-y","-f","concat","-safe","1",
                    "-i",str(listing),"-map","0:v:0","-map","0:a:0","-c:v","copy",
                    "-c:a","aac","-b:a","192k","-movflags","+faststart",str(combined)],
                    check=True,capture_output=True,text=True)
                verified=probe_clip(combined)
                error=verify_duration(verified,manifest["planning"]["estimated_duration_seconds"])
                if media_sha256(video)!=manifest["source"]["sha256"]:
                    raise ValueError("Source changed during assembly")
                if hashlib.sha256(Path(analysis_path).read_bytes()).hexdigest()!=manifest["shared_analysis"]["sha256"]:
                    raise ValueError("Analysis changed during assembly")
                new_hash=media_sha256(combined)
                if force and output.exists():
                    if output.is_symlink() or media_sha256(output)!=old_hash:
                        raise ValueError("Output changed during assembly")
                    os.replace(combined,output)
                else:
                    os.link(combined,output)
                manifest["assembly"].update(status="complete",verification=verified,assembled_segment_count=len(manifest["segments"]),
                    actual_duration_seconds=verified["duration_seconds"],duration_error_seconds=error,output_sha256=new_hash)
                for row in manifest["segments"]:
                    row["status"]="assembled"
            except (OSError,ValueError,subprocess.SubprocessError) as exc:
                manifest["assembly"].update(status="failed",error=getattr(exc,"stderr",None) or str(exc))
    if manifest["assembly"]["status"]=="failed" and output.exists() and old_hash and media_sha256(output)==old_hash:
        manifest["assembly"]["retained_previous_output"]=dict(sha256=old_hash,plan_signature=prior["plan_signature"])
    save_manifest(manifest,manifest_path,original)
    return directory,manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("video",type=Path)
    parser.add_argument("--analysis",type=Path,required=True)
    parser.add_argument("--output-root",type=Path,default=Path("output"))
    parser.add_argument("--seconds-before",type=float,default=15)
    parser.add_argument("--seconds-after",type=float,default=15)
    parser.add_argument("--merge-gap",type=float,default=5)
    parser.add_argument("--dry-run",action="store_true")
    parser.add_argument("--force",action="store_true")
    args=parser.parse_args(argv)
    try:
        directory,manifest=export_longform(args.video,args.analysis,output_root=args.output_root,
            seconds_before=args.seconds_before,seconds_after=args.seconds_after,merge_gap=args.merge_gap,
            dry_run=args.dry_run,force=args.force)
    except (ValueError,OSError,subprocess.SubprocessError) as exc:
        parser.exit(1,f"Long-form export failed: {exc}\n")
    print(f"Preselected {manifest['planning']['selection_provenance']['detector']} anchors: "
          f"{manifest['planning']['candidate_anchors']}")
    for row in manifest["segments"]:
        print(f"[{row['start']}, {row['end']}] {row['duration']}s: {row['status']}")
    actual=manifest["assembly"]["actual_duration_seconds"]
    actual_label="not assembled" if actual is None else f"{actual}s"
    print(f"Expected {manifest['planning']['estimated_duration_seconds']}s; "
          f"actual {actual_label}; {manifest['assembly']['status']}")
    print(directory)
    if manifest["assembly"]["error"]:
        print(manifest["assembly"]["error"])
    return int(manifest["assembly"]["status"]=="failed")


if __name__=="__main__":
    raise SystemExit(main())
