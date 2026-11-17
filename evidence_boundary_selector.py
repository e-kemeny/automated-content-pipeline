"""Experimental speech-continuity boundary selector; no human labels in prediction."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from copy import deepcopy

from gameplay_boundary_evaluation import validate_plan
from shared_analysis import validate_analysis
from transcription import validate_segments
from multimodal_timeline import read_json, check_provenance
from clip_boundary_experiment import match_source
from source_identity import canonical

POLICY = dict(version=1,feature="cut endpoints strictly inside saved ASR intervals",
              score="negative number of cut endpoints (0, -1, -2); higher is better",
              selection="unique maximum only; ties or no intersecting speech abstain",
              weights=None,semantic_event_claim=False)


def predict(plan, analysis):
    # Reject possible human-annotation inputs BEFORE producer reconstruction.
    if not isinstance(plan,dict) or plan.get("inputs",{}).get("proposals") is not None:
        raise ValueError("Selector accepts only original/fixed-offset plans, never narrative/human proposals")
    validate_plan(plan)
    analysis=validate_analysis(analysis)
    match_source(analysis["source_video"],plan["inputs"]["verified_source"])
    if analysis["candidate_windows"] != plan["inputs"]["analysis"]["candidate_windows"]:
        raise ValueError("Evidence candidate mappings differ from plan")
    candidates=plan["candidates"]
    if len(candidates)!=5 or len(plan["clips"])!=20:
        raise ValueError("V1 requires five candidates and twenty variants")
    for i,c in enumerate(candidates):
        if c["candidate_index"]!=i or [v["label"] for v in c["variants"]]!=["original","earlier_start","later_end","both"]:
            raise ValueError("Duplicate/missing candidate variants")
    transcript=analysis["transcript"]
    provenance=transcript["provenance"]
    check_provenance(provenance,analysis["source_video"])
    if transcript["status"]=="analyzed":
        if (provenance.get("backend")!="faster-whisper" or not provenance.get("model_id")
                or not provenance.get("model_revision")
                or provenance.get("source_sha256")!=analysis["source_video"].get("sha256")
                or provenance.get("source_duration_seconds")!=analysis["source_video"]["duration_seconds"]):
            raise ValueError("Require source-bound cached ASR provenance")
    segments=validate_segments(transcript["data"],analysis["source_video"]["duration_seconds"])
    # Only this whitelisted machine evidence is exposed to scoring.
    timings=[dict(segment_index=i,start=s["start"],end=s["end"])
             for i,s in enumerate(segments) if s["text"].strip() and s["end"]>s["start"]]
    clips={c["clip_id"]:c for c in plan["clips"]}
    decisions=[]
    for c in candidates:
        rows=[]
        for v in c["variants"]:
            clip=clips[v["clip_id"]]
            crossing={side:[s["segment_index"] for s in timings if s["start"]<clip[side]<s["end"]]
                      for side in ("start","end")}
            overlapping=[s["segment_index"] for s in timings if s["start"]<clip["end"] and s["end"]>clip["start"]]
            available=transcript["status"]=="analyzed" and bool(timings)
            rows.append(dict(label=v["label"],variant_id=v["variant_id"],clip_id=v["clip_id"],
                start=clip["start"],end=clip["end"],score=-sum(bool(ids) for ids in crossing.values()) if available else None,
                cut_segment_indices=crossing,overlapping_segment_indices=overlapping))
        has_context=any(r["overlapping_segment_indices"] for r in rows)
        best=max((r["score"] for r in rows if r["score"] is not None),default=None)
        ties=[r["label"] for r in rows if r["score"]==best] if best is not None else []
        selected=ties[0] if has_context and len(ties)==1 else None
        decisions.append(dict(candidate_index=c["candidate_index"],candidate_id=c["candidate_id"],
            selected_label=selected,status="selected" if selected else "abstained",
            reason="unique speech-continuity maximum" if selected else
                   ("missing_or_no_local_speech_evidence" if not has_context else "tied_best_scores"),
            tied_best_labels=ties,variants=rows))
    result=dict(schema_version=1,artifact_type="evidence-boundary-predictions",plan_id=plan["plan_id"],
        source_identity=deepcopy(plan["source_identity"]),policy=deepcopy(POLICY),
        machine_evidence=dict(status=transcript["status"],segment_count=len(segments),
            provenance=deepcopy(provenance),timings=timings,
            transcript_sha256=hashlib.sha256(canonical(transcript)).hexdigest()),
        excluded_signals=["human ratings/preferences/notes","language scores","CLIP semantic hypotheses",
                          "sparse legacy diagnostics","OCR/fusion unavailable"],
        candidates=decisions)
    return result


def evaluate(plan, analysis, benchmark_path):
    """Freeze canonical predictions BEFORE importing or loading human labels."""
    frozen=canonical(predict(plan,analysis))
    from human_boundary_benchmark import load_benchmark
    human=load_benchmark(benchmark_path)
    prediction=json.loads(frozen)
    if human["plan_id"]!=prediction["plan_id"]:
        raise ValueError("Human benchmark belongs to a different plan/source")
    aliases={"original":"original","earlier":"earlier_start","later":"later_end","both":"both"}
    comparisons=[]
    for decision,preference in zip(prediction["candidates"],human["human_preferences"]):
        if decision["candidate_index"]!=preference["candidate_index"]:
            raise ValueError("Human candidate mapping mismatch")
        expected=aliases[preference["variant"]]
        chosen=decision["selected_label"]
        comparisons.append(dict(candidate_index=decision["candidate_index"],predicted=chosen,
            human_preference=expected,provisional=preference["provisional"],
            outcome="abstention" if chosen is None else "agreement" if chosen==expected else "disagreement",
            original_baseline_agrees=expected=="original"))
    definitive=[r for r in comparisons if not r["provisional"]]
    return dict(schema_version=1,artifact_type="evidence-boundary-evaluation",
        frozen_prediction_sha256=hashlib.sha256(frozen).hexdigest(),predictions=prediction,
        comparison=comparisons,definitive_counts={k:sum(r["outcome"]==k for r in definitive)
                    for k in ("agreement","disagreement","abstention")},
        original_baseline=dict(agreements=sum(r["original_baseline_agrees"] for r in definitive),
                               total=len(definitive),provisional_reported_separately=True),
        limitations=["In-memory canonical freeze precedes human benchmark loading; no persistent output writes.",
          "Prior human results were known in project history; this is exploratory, not blinded or held-out validation.",
          "Speech boundaries are not gameplay boundaries; ASR gaps do not prove silence or event completion.",
          "No calibrated confidence, significance, generalization or quality improvement claim."])


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command",choices=("predict","evaluate"))
    parser.add_argument("--plan",type=Path,required=True)
    parser.add_argument("--analysis",type=Path,required=True)
    parser.add_argument("--benchmark",type=Path)
    args=parser.parse_args(argv)
    if (args.command=="evaluate") != (args.benchmark is not None):
        parser.error("--benchmark is required only for evaluate")
    try:
        plan,analysis=read_json(args.plan),read_json(args.analysis)
        result=predict(plan,analysis) if args.command=="predict" else evaluate(plan,analysis,args.benchmark)
        print(json.dumps(result,sort_keys=True,indent=2,allow_nan=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("FAIL: boundary selector: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
