"""Reproducible experimental clip comparisons; no automatic export or ratings."""
import argparse
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile

import clip_boundary_experiment as boundary
import narrative_clip_boundaries as narrative
from shared_analysis import validate_analysis
from highlight_evaluation import digest, publish
from source_identity import canonical
from multimodal_timeline import read_json, json_value

METRICS = ("action_completeness", "pacing", "overall_watchability")
POSITIONS = ("too_early", "too_late", "appropriate")
ROOT = Path(__file__).resolve().parent


def build_plan(analysis, verified_source, *, experiment=None, proposals=None):
    analysis = validate_analysis(analysis)
    base = boundary.build_plan(analysis, verified_source, 0, 0)
    try:
        if experiment is not None:
            boundary.validate_plan(experiment)
            expected = boundary.build_plan(analysis, verified_source, **experiment["offsets"])
            if canonical(expected) != canonical(experiment):
                raise ValueError("Boundary experiment does not match analysis/source")
        if proposals is not None:
            policy = proposals["policy"]
            expected = narrative.build_plan(**proposals["inputs"],
                **{k:policy[k] for k in ("min_duration","max_duration","max_extension","heuristic_padding")})
            if canonical(expected) != canonical(proposals) or canonical(proposals["inputs"]["analysis"]) != canonical(analysis):
                raise ValueError("Narrative proposals do not match validated analysis")
        clips, candidates = [], []
        by_bounds = {}
        for row in base["candidates"]:
            i = row["candidate_index"]
            options = [dict(label="original", window=row["variants"][0], provenance=dict(input="analysis"))]
            if experiment is not None:
                options += [dict(label=v["name"], window=v,
                    provenance=dict(input="experiment",plan_id=experiment["plan_id"],variant_id=v["variant_id"]))
                    for v in experiment["candidates"][i]["variants"] if v["name"] != "original"]
            narrative_status = "unavailable"
            if proposals is not None:
                proposed = proposals["candidates"][i]
                narrative_status = "changed" if proposed["changed"] else "unchanged"
                options.append(dict(label="narrative",window=proposed["proposed"],
                    provenance=dict(input="proposals",plan_id=proposals["plan_id"],
                        candidate_id=proposed["candidate_id"],status=proposed["status"],reason=proposed["reason"])))
            variants = []
            for option in options:
                w = option["window"]
                bounds = (w["start"],w["end"])
                if not 0 <= bounds[0] < bounds[1] <= verified_source["duration_seconds"] or w["duration"] != bounds[1]-bounds[0]:
                    raise ValueError("Invalid variant bounds/duration")
                if bounds not in by_bounds:
                    cid = digest(dict(source_identity=base["source_identity"],start=bounds[0],end=bounds[1]))
                    clip = dict(clip_id=cid,start=bounds[0],end=bounds[1],duration=w["duration"],
                                output_filename="clip_"+cid+".mp4",references=[])
                    by_bounds[bounds] = clip
                    clips.append(clip)
                clip = by_bounds[bounds]
                variant_id = digest(dict(candidate_id=row["candidate_id"],label=option["label"],clip_id=clip["clip_id"]))
                ref = dict(candidate_index=i,variant_id=variant_id,label=option["label"],
                           provenance=option["provenance"])
                clip["references"].append(deepcopy(ref))
                variants.append(dict(ref,clip_id=clip["clip_id"]))
            candidates.append(dict(candidate_index=i,candidate_id=row["candidate_id"],
                original_candidate=deepcopy(row["original_candidate"]),narrative_status=narrative_status,variants=variants))
        result = dict(schema_version=1,artifact_type="gameplay-boundary-evaluation-plan",
            inputs=deepcopy(dict(analysis=analysis,verified_source=verified_source,
                                experiment=experiment,proposals=proposals)),
            source_identity=base["source_identity"],candidate_provenance=base["candidate_provenance"],
            candidates=candidates,clips=clips,
            limitations=["Descriptive paired reviews only; no statistical significance or generalization claim.",
                         "Identical windows share one rating; candidates and labels are not independent observations.",
                         "Narrative label means a supplied proposal, not a proven narrative improvement."])
        result["plan_id"] = digest(result)
        return result
    except (KeyError,TypeError,IndexError) as exc:
        raise ValueError("Malformed evaluation inputs") from exc


def validate_plan(plan):
    try:
        json_value(plan)
        if canonical(plan) != canonical(build_plan(**plan["inputs"])):
            raise ValueError("Evaluation plan mismatch")
    except (KeyError,TypeError) as exc:
        raise ValueError("Malformed evaluation plan") from exc
    return plan


def review_template(plan):
    validate_plan(plan)
    return dict(schema_version=1,artifact_type="gameplay-boundary-reviews",plan_id=plan["plan_id"],
        clips=[dict(clip_id=c["clip_id"],output_filename=c["output_filename"],
                    ratings={m:None for m in METRICS},starts=None,ends=None,notes="") for c in plan["clips"]])


def compare(plan, reviews):
    expected = review_template(plan)
    try:
        json_value(reviews)
        blank = deepcopy(reviews)
        for row in blank["clips"]:
            if set(row["ratings"]) != set(METRICS):
                raise ValueError("Missing/unknown rating metrics")
            for value in row["ratings"].values():
                if value is not None and (type(value) is not int or not 1 <= value <= 5):
                    raise ValueError("Ratings must be null or integers 1-5")
            if any(row[k] is not None and row[k] not in POSITIONS for k in ("starts","ends")):
                raise ValueError("Invalid boundary judgment")
            if not isinstance(row["notes"],str):
                raise ValueError("Notes must be text")
            row.update(ratings={m:None for m in METRICS},starts=None,ends=None,notes="")
        if canonical(blank) != canonical(expected):
            raise ValueError("Review template does not match plan")
    except (KeyError,TypeError) as exc:
        raise ValueError("Malformed reviews") from exc
    ratings = {r["clip_id"]:r for r in reviews["clips"]}
    pairs, identical = [], []
    for candidate in plan["candidates"]:
        original = candidate["variants"][0]["clip_id"]
        seen = {}
        for v in candidate["variants"][1:]:
            seen.setdefault(v["clip_id"],[]).append(v["label"])
        for cid,labels in seen.items():
            if cid == original:
                identical.append(dict(candidate_index=candidate["candidate_index"],labels=labels))
                continue
            diffs = {m:None if ratings[original]["ratings"][m] is None or ratings[cid]["ratings"][m] is None
                     else ratings[cid]["ratings"][m]-ratings[original]["ratings"][m] for m in METRICS}
            pairs.append(dict(candidate_index=candidate["candidate_index"],alternative_labels=labels,
                original_clip_id=original,alternative_clip_id=cid,differences=diffs,
                complete=all(v is not None for v in diffs.values())))
    metrics = {}
    for m in METRICS:
        values = [p["differences"][m] for p in pairs if p["differences"][m] is not None]
        metrics[m] = dict(valid_rated_pairs=len(values),unrated_pairs=len(pairs)-len(values),
                          mean_paired_difference=sum(values)/len(values) if values else None)
    missing = [dict(clip_id=r["clip_id"],fields=[m for m in METRICS if r["ratings"][m] is None]
                    +[k for k in ("starts","ends") if r[k] is None]) for r in reviews["clips"]]
    return dict(schema_version=1,artifact_type="gameplay-boundary-comparison",plan_id=plan["plan_id"],
        reviews_sha256=digest(reviews),valid_rated_pairs=sum(p["complete"] for p in pairs),
        unrated_or_partial_pairs=sum(not p["complete"] for p in pairs),
        metrics=metrics,pairs=pairs,identical_to_original=identical,
        incomplete_evaluations=[r for r in missing if r["fields"]],limitations=plan["limitations"])


def export_plan(plan, video, destination):
    validate_plan(plan)
    destination = Path(destination)
    resolved = destination.resolve()
    if destination.exists() or destination.is_symlink():
        raise ValueError("Export requires a new destination; no overwrite")
    if resolved.is_relative_to(ROOT):
        parts = resolved.relative_to(ROOT).parts
        if len(parts)<2 or parts[0]!="output" or not parts[1].startswith("boundary_experiment"):
            raise ValueError("Use isolated output/boundary_experiment* directory")
    video = Path(video)
    actual = boundary.verify_video(video,plan["inputs"]["analysis"]["source_video"])
    boundary.match_source(plan["inputs"]["verified_source"],actual)
    before = boundary.stat_identity(video)
    destination.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".evaluation-stage-",dir=destination.parent) as directory:
        stage = Path(directory)
        exported = []
        for clip in plan["clips"]:
            details = boundary.encode_clip(video,stage/clip["output_filename"],clip["start"],clip["duration"])
            exported.append(dict(clip,**details,status="exported"))
        if boundary.stat_identity(video) != before:
            raise ValueError("Source changed during export")
        manifest = dict(schema_version=1,artifact_type="gameplay-boundary-export",
                        plan_id=plan["plan_id"],status="complete",clips=exported)
        for name, data in (("evaluation_plan.json",plan),("reviews.json",review_template(plan)),
                           ("export_manifest.json",manifest)):
            publish(data,stage/name,[])
        if destination.exists() or destination.is_symlink():
            raise ValueError("Destination appeared during export")
        os.rename(stage,destination)
    return manifest


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command",required=True)
    p = commands.add_parser("plan")
    p.add_argument("--analysis",type=Path,required=True)
    p.add_argument("--video",type=Path,required=True)
    p.add_argument("--experiment",type=Path)
    p.add_argument("--proposals",type=Path)
    for name in ("export","review-template","compare"):
        p = commands.add_parser(name)
        p.add_argument("--plan",type=Path,required=True)
        if name=="export":
            p.add_argument("--video",type=Path,required=True)
            p.add_argument("--output-root",type=Path,required=True)
        if name=="compare":
            p.add_argument("--reviews",type=Path,required=True)
    for name in ("plan","review-template","compare"):
        commands.choices[name].add_argument("--output",type=Path,required=True)
    args = parser.parse_args(argv)
    try:
        if args.command=="plan":
            analysis = read_json(args.analysis)
            validate_analysis(analysis)
            actual = boundary.verify_video(args.video,analysis["source_video"])
            options = {k:read_json(getattr(args,k)) for k in ("experiment","proposals") if getattr(args,k)}
            result = build_plan(analysis,actual,**options)
            inputs = [args.analysis,args.video]+[getattr(args,k) for k in options]
        else:
            plan = validate_plan(read_json(args.plan))
            if args.command=="export":
                result = export_plan(plan,args.video,args.output_root)
                print(f"Exported {len(result['clips'])} unique review clips")
                return 0
            result = review_template(plan) if args.command=="review-template" else compare(plan,read_json(args.reviews))
            inputs = [args.plan]+([args.reviews] if args.command=="compare" else [])
        publish(result,args.output,inputs)
        print(f"Saved {args.output}")
        return 0
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(f"FAIL: gameplay boundary evaluation: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
