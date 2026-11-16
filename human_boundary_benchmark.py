"""Read-only human boundary benchmark validation and descriptive summary."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys

from gameplay_boundary_evaluation import validate_plan, review_template, compare, METRICS
from multimodal_timeline import read_json
from source_identity import canonical

LABELS = {"original":"original","earlier":"earlier_start","later":"later_end","both":"both"}
DEFAULT = Path(__file__).resolve().parent/"benchmarks"/"boundary_review_v1"


def import_reviews(plan, manifest, rows):
    """Map explicit human candidate/variant labels through the validated plan."""
    try:
        validate_plan(plan)
        if (manifest["schema_version"] != 1 or manifest["artifact_type"] != "gameplay-boundary-export"
                or manifest["status"] != "complete" or manifest["plan_id"] != plan["plan_id"]):
            raise ValueError("Export manifest does not match plan")
        if len(plan["clips"]) != 20 or len(manifest["clips"]) != 20:
            raise ValueError("Benchmark requires exactly 20 clips")
        exports = {r["clip_id"]:r for r in manifest["clips"]}
        if len(exports) != 20 or set(exports) != {r["clip_id"] for r in plan["clips"]}:
            raise ValueError("Duplicate/missing exported clips")
        for clip in plan["clips"]:
            exported = exports[clip["clip_id"]]
            if any(exported.get(k) != v for k,v in clip.items()) or exported["status"] != "exported":
                raise ValueError("Export mapping mismatch")
            checksum = exported["sha256"]
            if not isinstance(checksum,str) or len(checksum)!=64 or any(c not in "0123456789abcdef" for c in checksum):
                raise ValueError("Invalid exported clip checksum")
        if [c["candidate_index"] for c in plan["candidates"]] != list(range(5)):
            raise ValueError("Expected five ordered candidates")
        mapping = {}
        for c in plan["candidates"]:
            if [v["label"] for v in c["variants"]] != list(LABELS.values()):
                raise ValueError("Expected original/earlier/later/both variants")
            for label, internal in LABELS.items():
                mapping[c["candidate_index"],label] = next(v["clip_id"] for v in c["variants"] if v["label"]==internal)
        if len(set(mapping.values())) != 20:
            raise ValueError("Benchmark expects distinct variant clips")
        result = review_template(plan)
        by_id = {r["clip_id"]:r for r in result["clips"]}
        seen = set()
        for row in rows:
            if set(row) != {"candidate_index","variant","ratings","starts","ends","notes"}:
                raise ValueError("Malformed human review fields")
            if type(row["candidate_index"]) is not int:
                raise ValueError("Candidate index must be integer")
            key = row["candidate_index"],row["variant"]
            if key not in mapping or key in seen:
                raise ValueError("Unknown or duplicate human variant")
            seen.add(key)
            by_id[mapping[key]].update({k:deepcopy(row[k]) for k in ("ratings","starts","ends","notes")})
        if seen != set(mapping):
            raise ValueError("Missing human reviews")
        report = compare(plan,result)
        if report["valid_rated_pairs"] != 15 or report["incomplete_evaluations"]:
            raise ValueError("Benchmark requires 20 complete reviews and 15 rated pairs")
        return result
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed benchmark inputs") from exc


def summarize(plan, reviews, preferences):
    report = compare(plan,reviews)
    ratings = {r["clip_id"]:r["ratings"] for r in reviews["clips"]}
    clips = {r["clip_id"]:r for r in plan["clips"]}
    means, differences = {}, {}
    for label,internal in LABELS.items():
        values = {m:[] for m in METRICS}
        deltas = {m:[] for m in METRICS}
        for c in plan["candidates"]:
            original = ratings[c["variants"][0]["clip_id"]]
            current = ratings[next(v["clip_id"] for v in c["variants"] if v["label"]==internal)]
            for m in METRICS:
                if current[m] is not None:
                    values[m].append(current[m])
                if current[m] is not None and original[m] is not None:
                    deltas[m].append(current[m]-original[m])
        means[label] = {m:sum(v)/len(v) if v else None for m,v in values.items()}
        if label!="original":
            differences[label] = {m:sum(v)/len(v) if v else None for m,v in deltas.items()}
    preferred = []
    if len(preferences)!=5 or [p["candidate_index"] for p in preferences]!=list(range(5)):
        raise ValueError("Expected five ordered human preferences")
    for p,c in zip(preferences,plan["candidates"]):
        if p["variant"] not in LABELS or type(p["provisional"]) is not bool or not isinstance(p["notes"],str):
            raise ValueError("Invalid human preference")
        clip_id = next(v["clip_id"] for v in c["variants"] if v["label"]==LABELS[p["variant"]])
        preferred.append(dict(p,start=clips[clip_id]["start"],end=clips[clip_id]["end"],clip_id=clip_id))
    return dict(schema_version=1,benchmark="boundary_review_v1",plan_id=plan["plan_id"],
        coverage=dict(reviewed_clips=len(reviews["clips"]),valid_rated_pairs=report["valid_rated_pairs"],
                      incomplete_evaluations=report["incomplete_evaluations"]),
        means=means,paired_differences=differences,human_preferences=preferred,
        per_candidate_pairs=report["pairs"],
        limitations=["One already-edited recording, five candidate families; no significance or generalization claim.",
                     "Human preferences are supplied labels, not inferred numeric winners.",
                     "Notes are supplied cleaned paraphrases; the supplied request is preserved verbatim.",
                     "No gameplay recognition accuracy or production behavior improvement established."])


def load_benchmark(directory=DEFAULT):
    root = Path(directory)
    metadata = read_json(root/"benchmark.json")
    if type(metadata.get("schema_version")) is not int or metadata["schema_version"]!=1 or metadata.get("benchmark")!="boundary_review_v1":
        raise ValueError("Unsupported benchmark schema")
    expected = {"evaluation_plan.json","export_manifest.json","human_reviews.json","reviews.json","preferences.json","supplied_request.txt"}
    if set(metadata["files"]) != expected:
        raise ValueError("Missing/unknown benchmark files")
    for name,checksum in metadata["files"].items():
        if hashlib.sha256((root/name).read_bytes()).hexdigest()!=checksum:
            raise ValueError("Benchmark file checksum mismatch: "+name)
    plan = read_json(root/"evaluation_plan.json")
    reviews = import_reviews(plan,read_json(root/"export_manifest.json"),read_json(root/"human_reviews.json"))
    if canonical(reviews)!=canonical(read_json(root/"reviews.json")):
        raise ValueError("Imported reviews disagree with preserved human rows")
    return summarize(plan,reviews,read_json(root/"preferences.json"))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmark",type=Path,default=DEFAULT)
    args=parser.parse_args(argv)
    try:
        print(json.dumps(load_benchmark(args.benchmark),sort_keys=True,indent=2,allow_nan=False))
        return 0
    except (OSError,ValueError,KeyError,TypeError) as exc:
        print("FAIL: boundary benchmark: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
