"""Isolated heuristic boundary plans, optional exports, and human comparisons."""
import argparse
from copy import deepcopy
from itertools import combinations
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

from shared_analysis import create_analysis, validate_analysis
from source_identity import canonical, validate_identity
from highlight_evaluation import digest, publish, SCALE
from multimodal_timeline import read_json, number, source_metadata, json_value, check_provenance
from export_shorts import probe_clip, verify_duration
from transcription import probe_media, media_sha256

ROOT=Path(__file__).resolve().parent
VARIANTS=("original","earlier_start","later_end","both")
LIMITATIONS=[
    "Fixed offsets are heuristic boundary experiments, not AI-detected semantic boundaries.",
    "Longer clips are not assumed better; comparisons require explicit human reviews.",
    "Descriptive results from a small selected sample; no significance or model-improvement claim.",
    "Stored candidate order is not a ranking; overlapping and duplicate candidates remain separate.",
    "Historical baseline ratings are context only; every new comparison rating starts null.",
]


def stat_identity(path):
    s=path.stat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def match_source(claim,actual):
    source_metadata(claim)
    source_metadata(actual)
    if not claim.get("sha256") or claim["sha256"]!=actual.get("sha256"):
        raise ValueError("A matching source SHA-256 is required")
    if "duration_seconds" not in claim or abs(claim["duration_seconds"]-actual["duration_seconds"])>1e-6:
        raise ValueError("Source duration mismatch")
    for key in ("width","height","fps","size_bytes"):
        if key in claim and claim[key]!=actual.get(key):
            raise ValueError(f"Source metadata mismatch: {key}")


def verify_video(video,claim):
    """Read-only source verification: one source hash/probe, never analysis."""
    video=Path(video)
    if video.is_symlink() or not video.is_file():
        raise ValueError("Source must be an existing non-symlink video")
    video=video.resolve()
    before=stat_identity(video)
    actual=probe_media(video)  # Existing audio/video metadata and one SHA-256 pass.
    actual["size_bytes"]=video.stat().st_size
    if stat_identity(video)!=before:
        raise ValueError("Source changed while verifying")
    match_source(claim,actual)
    return actual


def build_plan(analysis,verified_source,seconds_before=3,seconds_after=3):
    """Pure planning from metadata returned by verify_video; no implicit verification."""
    analysis=validate_analysis(analysis)
    source=analysis["source_video"]
    match_source(source,verified_source)
    for offset in (seconds_before,seconds_after):
        if not 0<=number(offset)<=10:
            raise ValueError("Offsets must be finite numbers from 0 to 10 seconds")
    identity=validate_identity(dict(version=1,algorithm="sha256",digest=verified_source["sha256"],
        size_bytes=verified_source["size_bytes"],
        media={k:verified_source[k] for k in ("duration_seconds","width","height","fps") if k in verified_source}))
    if not {"duration_seconds","width","height"}<=identity["media"].keys():
        raise ValueError("Verified video metadata is incomplete")
    envelope=analysis["candidate_windows"]
    if envelope["status"]!="analyzed" or not envelope["data"]:
        raise ValueError("Analyzed candidate windows are required")
    check_provenance(envelope["provenance"],source)
    duration=identity["media"]["duration_seconds"]
    candidates=[]
    for index,row in enumerate(envelope["data"]):
        start,end=row["start"],row["end"]
        if not 0<=start<end<=duration:
            raise ValueError("Original window must have positive duration within verified source")
        if "score" in row:
            number(row["score"])
        cid=digest(dict(index=index,source_identity=identity,candidate=row))
        variants=[]
        for name in VARIANTS:
            proposed_start=max(0,start-seconds_before) if name in ("earlier_start","both") else start
            proposed_end=min(duration,end+seconds_after) if name in ("later_end","both") else end
            variants.append(dict(variant_id=digest(dict(candidate_id=cid,name=name,start=proposed_start,end=proposed_end)),name=name,
                start=proposed_start,end=proposed_end,duration=proposed_end-proposed_start,
                applied_start_offset=proposed_start-start,applied_end_offset=proposed_end-end))
        candidates.append(dict(candidate_index=index,candidate_id=cid,original_candidate=deepcopy(row),
                               original_audio_score=row.get("score"),variants=variants))
    plan=dict(schema_version=1,artifact_type="clip-boundary-plan",
        method="heuristic_fixed_offsets",source_video=deepcopy(source),source_identity=identity,
        duration_basis="source content and duration verified at plan creation; export rechecks",
        analysis_schema_version=analysis["schema_version"],candidate_provenance=deepcopy(envelope["provenance"]),
        offsets=dict(seconds_before=seconds_before,seconds_after=seconds_after),candidates=candidates)
    plan["plan_id"]=digest(plan)
    return plan


def validate_plan(plan):
    try:
        json_value(plan)
        analysis=create_analysis(plan["source_video"])
        analysis["candidate_windows"]=dict(status="analyzed",provenance=plan["candidate_provenance"],
                                           data=[r["original_candidate"] for r in plan["candidates"]])
        identity=validate_identity(plan["source_identity"])
        actual=dict(sha256=identity["digest"],size_bytes=identity["size_bytes"],**identity["media"])
        expected=build_plan(analysis,actual,**plan["offsets"])
        if canonical(plan)!=canonical(expected):
            raise ValueError("Plan is invalid or has been altered")
        return plan
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed boundary plan") from exc


def review_template(plan):
    validate_plan(plan)
    return dict(schema_version=1,artifact_type="clip-boundary-reviews",plan_id=plan["plan_id"],
        source_identity=deepcopy(plan["source_identity"]),rating_scale=deepcopy(SCALE),
        candidates=[dict(candidate_index=r["candidate_index"],candidate_id=r["candidate_id"],
            original_candidate=deepcopy(r["original_candidate"]),preferred_variant=None,notes="",
            variants=[dict(v,rating=None,notes="") for v in r["variants"]]) for r in plan["candidates"]])


def compare_reviews(plan,reviews):
    expected=review_template(plan)
    try:
        json_value(reviews)
        candidate_copy=deepcopy(reviews)
        if not isinstance(candidate_copy["candidates"],list):
            raise ValueError("Review candidates must be a list")
        for row in candidate_copy["candidates"]:
            if row["preferred_variant"] is not None and row["preferred_variant"] not in VARIANTS:
                raise ValueError("Invalid preferred variant")
            if not isinstance(row["notes"],str):
                raise ValueError("Notes must be text")
            row["preferred_variant"]=None
            row["notes"]=""
            for variant in row["variants"]:
                rating=variant["rating"]
                if rating is not None and (type(rating) is not int or not 1<=rating<=5):
                    raise ValueError("Ratings must be integers 1â€“5 or null")
                if not isinstance(variant["notes"],str):
                    raise ValueError("Notes must be text")
                variant.update(rating=None,notes="")
        if canonical(candidate_copy)!=canonical(expected):
            raise ValueError("Review template does not match the plan")
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed boundary review") from exc
    results=[]
    longer=dict(better=0,worse=0,tied=0,paired_comparisons=0)
    rated=reviewed=0
    for row in reviews["candidates"]:
        original=row["variants"][0]
        rated+=sum(v["rating"] is not None for v in row["variants"])
        reviewed+=bool(row["preferred_variant"] is not None or row["notes"].strip()
                       or any(v["rating"] is not None or v["notes"].strip() for v in row["variants"]))
        differences=[]
        for variant in row["variants"][1:]:
            delta=None if original["rating"] is None or variant["rating"] is None else variant["rating"]-original["rating"]
            duration_delta=variant["duration"]-original["duration"]
            differences.append(dict(variant=variant["name"],rating_difference=delta,duration_difference=duration_delta))
            if delta is not None and duration_delta>0:
                longer["paired_comparisons"]+=1
                longer["better" if delta>0 else "worse" if delta<0 else "tied"]+=1
        ties=[[a["name"],b["name"]] for a,b in combinations(row["variants"],2)
              if a["rating"] is not None and a["rating"]==b["rating"]]
        results.append(dict(candidate_index=row["candidate_index"],candidate_id=row["candidate_id"],
            preferred_variant=row["preferred_variant"],notes=row["notes"],variants=deepcopy(row["variants"]),
            differences_from_original=differences,tied_variants=ties,
            missing_ratings=[v["name"] for v in row["variants"] if v["rating"] is None]))
    return dict(schema_version=1,artifact_type="clip-boundary-comparison",plan_id=plan["plan_id"],
        reviews_content_sha256=digest(reviews),source_identity=deepcopy(plan["source_identity"]),
        candidates_reviewed=reviewed,variants_rated=rated,missing_ratings=4*len(results)-rated,
        longer_duration_comparison=longer,
        longer_duration_observation=("No paired reviews of genuinely longer variants." if not longer["paired_comparisons"] else
            "Among longer paired variants: {better} rated higher, {worse} lower, {tied} tied; descriptive only.".format(**longer)),
        candidates=results,limitations=list(LIMITATIONS))


def export_plan(plan,video,output_root):
    """Stage all variants, verify them, then publish a new isolated directory."""
    validate_plan(plan)
    destination=Path(output_root)
    if destination.is_symlink() or destination.exists():
        raise ValueError("Export requires a new, nonexistent output directory; no overwrite or repair")
    resolved=destination.resolve()
    if resolved.is_relative_to(ROOT):
        relative=resolved.relative_to(ROOT)
        if len(relative.parts)<2 or relative.parts[0]!="output" or not relative.parts[1].startswith("boundary_experiment"):
            raise ValueError("Repository exports must be isolated under output/boundary_experiment*")
    video=Path(video)
    # verify_video checks existence and live content; metadata alone never suffices.
    before=stat_identity(video)
    actual=verify_video(video,plan["source_video"])
    video=video.resolve()
    expected=dict(sha256=plan["source_identity"]["digest"],size_bytes=plan["source_identity"]["size_bytes"],
                  **plan["source_identity"]["media"])
    match_source(expected,actual)
    for row in plan["candidates"]:
        for variant in row["variants"]:
            if not 0<=variant["start"]<variant["end"]<=actual["duration_seconds"]:
                raise ValueError("Variant exceeds actual source duration")
    destination.parent.mkdir(parents=True,exist_ok=True)
    manifest=dict(schema_version=1,artifact_type="clip-boundary-export",plan_id=plan["plan_id"],
                  source_identity=deepcopy(plan["source_identity"]),status="complete",clips=[])
    with tempfile.TemporaryDirectory(prefix=".boundary-stage-",dir=destination.parent) as directory:
        stage=Path(directory)
        for row in plan["candidates"]:
            for variant in row["variants"]:
                filename=f"candidate_{row['candidate_index']:03d}_{variant['name']}.mp4"
                target=stage/filename
                # Same horizontal H.264/AAC settings as Shorts; no reusable encoder function exists there.
                subprocess.run(["ffmpeg","-v","error","-nostdin","-n","-ss",str(variant["start"]),
                    "-i",str(video),"-t",str(variant["duration"]),"-map","0:v:0","-map","0:a:0",
                    "-c:v","libx264","-preset","fast","-crf","18","-pix_fmt","yuv420p",
                    "-c:a","aac","-b:a","192k","-movflags","+faststart",str(target)],
                    check=True,capture_output=True,text=True)
                probe=probe_clip(target)
                error=verify_duration(probe,variant["duration"])
                manifest["clips"].append(dict(candidate_index=row["candidate_index"],variant_id=variant["variant_id"],
                    variant=variant["name"],start=variant["start"],end=variant["end"],
                    output_filename=filename,verification=probe,duration_error_seconds=error,
                    sha256=media_sha256(target),status="exported"))
        if stat_identity(video)!=before:
            raise ValueError("Source changed during export")
        (stage/"boundary_export_manifest.json").write_text(json.dumps(manifest,sort_keys=True,indent=2,allow_nan=False)+"\n",
                                                         encoding="utf-8",newline="\n")
        if destination.exists() or destination.is_symlink():
            raise FileExistsError("Destination appeared during export")
        os.rename(stage,destination)  # Windows refuses an existing destination; no concurrent writers supported.
    return manifest


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    p=commands.add_parser("plan")
    p.add_argument("--analysis",type=Path,required=True)
    p.add_argument("--video",type=Path,required=True,help="Read-only identity/duration verification; no encoding")
    p.add_argument("--seconds-before",type=float,default=3)
    p.add_argument("--seconds-after",type=float,default=3)
    p=commands.add_parser("export")
    p.add_argument("--plan",type=Path,required=True)
    p.add_argument("--video",type=Path,required=True)
    p.add_argument("--output-root",type=Path,required=True)
    for name in ("review-template","compare"):
        p=commands.add_parser(name)
        p.add_argument("--plan",type=Path,required=True)
        if name=="compare": p.add_argument("--reviews",type=Path,required=True)
    for name in ("plan","review-template","compare"):
        p=commands.choices[name]
        p.add_argument("--output",type=Path,required=True)
        p.add_argument("--overwrite",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.command=="plan":
            analysis=read_json(args.analysis)
            validate_analysis(analysis)
            actual=verify_video(args.video,analysis["source_video"])
            result=build_plan(analysis,actual,args.seconds_before,args.seconds_after)
            inputs=[args.analysis,args.video]
        else:
            plan=validate_plan(read_json(args.plan))
            if args.command=="export":
                result=export_plan(plan,args.video,args.output_root)
                print(f"Exported {len(result['clips'])} variants to {args.output_root}")
                return 0
            result=(review_template(plan) if args.command=="review-template" else
                    compare_reviews(plan,read_json(args.reviews)))
            inputs=[args.plan]+([args.reviews] if args.command=="compare" else [])
        publish(result,args.output,inputs,args.overwrite)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(f"FAIL: boundary experiment: {exc}",file=sys.stderr)
        return 1
    print(f"Saved {args.output}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
