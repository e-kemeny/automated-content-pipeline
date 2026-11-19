"""Frozen experimental dense continuity rule; production and V1 remain unchanged."""
import argparse
from copy import deepcopy
from fractions import Fraction
import json
import math
from pathlib import Path
import subprocess
import sys

import dense_observations as dense
import evidence_boundary_selector as v1
from source_identity import file_identity, canonical
from highlight_evaluation import digest, publish
from multimodal_timeline import read_json

POLICY=dict(version=2,bin_seconds=1,scene_radius_seconds=0.5,audio_weight=0.5,motion_weight=0.5,
    formula="cut=(1-scene_near)*0.5*(min(A[t-1],A[t])/max(A)+min(M[t-1],M[t])/max(M)); score=-(cut_start+cut_end)/2",
    tie_abs_tolerance=1e-12,duration_bonus=0,selection="unique maximum; all variants require valid evidence")


def inspect_alignment(video, cache):
    """Read-only live content and initial decoded-clock checks, not extraction."""
    checksum,size=file_identity(video)
    identity=cache["source_identity"]
    if (checksum,size)!=(identity["digest"],identity["size_bytes"]):
        raise ValueError("Live source identity mismatch")
    first={}
    for name,stream in (("audio","a:0"),("video","v:0")):
        result=subprocess.run(["ffprobe","-v","error","-select_streams",stream,
            "-read_intervals","%+#8","-show_frames","-show_entries",
            "frame=pts_time,best_effort_timestamp_time","-of","json",str(video)],
            check=True,capture_output=True,text=True,timeout=30)
        frames=json.loads(result.stdout)["frames"]
        first[name]=float(frames[0]["best_effort_timestamp_time"]) if frames else None
    if file_identity(video)!=(checksum,size):
        raise ValueError("Source changed during alignment inspection")
    return dict(source_identity=deepcopy(identity),first_decoded_seconds=first,
                method="ffprobe first decoded frame; first eight packets; no time offset correction")


def alignment_ok(cache,audit):
    if audit["source_identity"]!=cache["source_identity"]:
        raise ValueError("Alignment audit source mismatch")
    if audit["first_decoded_seconds"]!={"audio":0.0,"video":0.0}:
        return False
    for kind in ("audio","video"):
        streams=[s for s in cache["stream_metadata"] if s.get("codec_type")==kind]
        if len(streams)!=1:
            return False
        try:
            if float(streams[0]["start_time"])!=0 or Fraction(streams[0]["time_base"])<=0:
                return False
        except (KeyError,ValueError,ZeroDivisionError):
            return False
    return True


def cut_features(t,audio,motion,scenes,max_audio,max_motion,aligned):
    reason=None
    if not aligned:reason="unsupported_or_unverified_clock_origin"
    elif not float(t).is_integer():reason="noninteger_boundary_not_supported_by_one_second_bins"
    elif any(k not in rows for rows in (audio,motion) for k in (int(t)-1,int(t))):
        reason="missing_adjacent_samples"
    elif max_audio<=0 or max_motion<=0:reason="uninformative_zero_activity_modality"
    if reason:return dict(second=t,penalty=None,reason=reason)
    before,after=int(t)-1,int(t)
    a=min(audio[before],audio[after])/max_audio
    m=min(motion[before],motion[after])/max_motion
    nearby=[deepcopy(s) for s in scenes if abs(s["time"]-t)<=POLICY["scene_radius_seconds"]]
    penalty=0.0 if nearby else (a+m)/2
    return dict(second=t,penalty=penalty,reason="coarse_continuity",
        audio=dict(before=audio[before],after=audio[after],global_max=max_audio,continuity=a),
        motion=dict(before=motion[before],after=motion[after],global_max=max_motion,continuity=m),
        scene_observations=nearby,scene_near=bool(nearby))


def predict(plan,cache,analysis,audit):
    dense.validate(cache)
    # Reuse V1's plan/source/candidate validation; no human inputs accepted.
    speech=v1.predict(plan,analysis)
    if cache["source_identity"]!=plan["source_identity"]:
        raise ValueError("Dense cache and plan source identities differ")
    aligned=alignment_ok(cache,audit)
    audio={r["second"]:r["volume"] for r in cache["full_observations"]["audio"]["amplitude_rows"]}
    motion={r["second"]:r["score"] for r in cache["motion_rows"]}
    scenes=cache["full_observations"]["scene_changes"]["data"]
    maximum_a=max(audio.values(),default=0)
    maximum_m=max(motion.values(),default=0)
    clips={c["clip_id"]:c for c in plan["clips"]}
    decisions=[]
    for candidate in plan["candidates"]:
        rows=[]
        for v in candidate["variants"]:
            c=clips[v["clip_id"]]
            evidence={side:cut_features(c[side],audio,motion,scenes,maximum_a,maximum_m,aligned)
                      for side in ("start","end")}
            penalties=[r["penalty"] for r in evidence.values()]
            score=None if None in penalties else -sum(penalties)/2
            rows.append(dict(label=v["label"],variant_id=v["variant_id"],clip_id=v["clip_id"],
                start=c["start"],end=c["end"],score=score,evidence=evidence))
        complete=all(r["score"] is not None for r in rows)
        best=max(r["score"] for r in rows) if complete else None
        ties=[r["label"] for r in rows if math.isclose(r["score"],best,rel_tol=0,
              abs_tol=POLICY["tie_abs_tolerance"])] if complete else []
        chosen=ties[0] if len(ties)==1 else None
        decisions.append(dict(candidate_index=candidate["candidate_index"],candidate_id=candidate["candidate_id"],
            selected_label=chosen,reason="unique_maximum" if chosen else "tie" if complete else "insufficient_evidence",
            tied_best_labels=ties,variants=rows))
    result=dict(schema_version=1,artifact_type="dense-boundary-predictions-v2",
        policy=deepcopy(POLICY),plan_id=plan["plan_id"],source_identity=deepcopy(plan["source_identity"]),
        alignment_audit=deepcopy(audit),alignment_supported=aligned,
        input_digests=dict(plan=digest(plan),dense=digest(cache),analysis=digest(analysis)),
        candidates=decisions,v1_predictions=speech,
        limitations=["One-second measurements are not frame-accurate event timing.",
          "Nearby scene changes are visual discontinuities, not confirmed transitions or resolutions.",
          "No duration preference or label tuning; hypotheses and human annotations excluded.",
          "Known benchmark history makes this exploratory, not blinded independent validation."])
    result["prediction_sha256"]=digest(result)
    return result


def validate_frozen(result):
    body=deepcopy(result)
    checksum=body.pop("prediction_sha256")
    if digest(body)!=checksum or result["policy"]!=POLICY or result["artifact_type"]!="dense-boundary-predictions-v2":
        raise ValueError("Frozen predictions/configuration modified")
    if [r["candidate_index"] for r in result["candidates"]]!=list(range(5)):
        raise ValueError("Invalid frozen candidate mapping")
    return result


def evaluate_file(path,benchmark):
    # A persisted, validated prediction artifact is mandatory before any label read.
    frozen=validate_frozen(read_json(path))
    before=canonical(frozen)
    from human_boundary_benchmark import load_benchmark
    human=load_benchmark(benchmark)
    if human["plan_id"]!=frozen["plan_id"]:
        raise ValueError("Benchmark plan/source mismatch")
    aliases={"original":"original","earlier":"earlier_start","later":"later_end","both":"both"}
    rows=[]
    for v2,speech,h in zip(frozen["candidates"],frozen["v1_predictions"]["candidates"],human["human_preferences"]):
        if not v2["candidate_index"]==speech["candidate_index"]==h["candidate_index"]:
            raise ValueError("Comparison mapping mismatch")
        expected=aliases[h["variant"]]
        def outcome(label):
            return "abstention" if label is None else "agreement" if label==expected else "disagreement"
        rows.append(dict(candidate_index=h["candidate_index"],human_preference=expected,provisional=h["provisional"],
            v2=v2["selected_label"],v1=speech["selected_label"],v2_outcome=outcome(v2["selected_label"]),
            v1_outcome=outcome(speech["selected_label"]),original_outcome=outcome("original"),
            evidence=deepcopy(v2["variants"])))
    totals={}
    for group,provisional in (("definitive",False),("provisional",True)):
        totals[group]={system:{status:sum(r["provisional"]==provisional and r[system+"_outcome"]==status for r in rows)
            for status in ("agreement","disagreement","abstention")} for system in ("v2","v1","original")}
    if canonical(frozen)!=before:raise ValueError("Predictions mutated during evaluation")
    return dict(prediction_sha256=frozen["prediction_sha256"],counts=totals,candidates=rows,
                limitations=frozen["limitations"])


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    sub=p.add_subparsers(dest="command",required=True)
    f=sub.add_parser("freeze")
    for name in ("plan","dense","analysis","video","output"):
        f.add_argument("--"+name,type=Path,required=True)
    e=sub.add_parser("evaluate")
    e.add_argument("--predictions",type=Path,required=True)
    e.add_argument("--benchmark",type=Path,required=True)
    args=p.parse_args(argv)
    try:
        if args.command=="freeze":
            if args.output.exists():raise ValueError("Frozen output exists; no overwrite")
            cache=dense.validate(read_json(args.dense))
            audit=inspect_alignment(args.video,cache)
            result=predict(read_json(args.plan),cache,read_json(args.analysis),audit)
            publish(result,args.output,[args.video,args.plan,args.dense,args.analysis])
            print("Frozen "+result["prediction_sha256"])
            for r in result["candidates"]:
                print(r["candidate_index"],r["selected_label"],[(v["label"],v["score"]) for v in r["variants"]])
        else:
            print(json.dumps(evaluate_file(args.predictions,args.benchmark),sort_keys=True,indent=2,allow_nan=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError,subprocess.SubprocessError) as exc:
        print("FAIL: V2 selector: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
