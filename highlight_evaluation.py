"""Offline descriptive evaluation of persisted candidates and human ratings."""
import argparse
from copy import deepcopy
import hashlib
from itertools import combinations
import json
from pathlib import Path
import sys

from shared_analysis import validate_analysis
from source_identity import canonical
from multimodal_timeline import read_json, json_value, source_metadata, check_provenance
from timeline_query import save_query
from inspect_candidate_evidence import validate_evidence

ROOT = Path(__file__).resolve().parent
SCORE_KEYS = {"Audio-only":"score", "Audio + Scene":"highlight_score",
              "Audio + Motion":"motion_highlight_score"}
SCALE = {"1":"Not worth retaining", "2":"Weak; substantial trimming/context needed",
         "3":"Usable with editing", "4":"Strong highlight", "5":"Standout highlight"}
LIMITATIONS = [
    "Descriptive exploratory results for these candidates and supplied ratings only.",
    "Stored candidate order is chronological, not evidence of score ranking.",
    "Scores are compared only within this artifact under explicit fixed-detector provenance.",
    "Selected candidates are not the complete candidate pool; results do not measure overall detector performance.",
    "Null ratings are missing; ties and incomparable pairs are excluded from strict pairwise agreement.",
    "Source identity is reported metadata, not independently verified video content.",
    "Missing evidence, event counts and signal amplitudes do not establish highlight quality.",
]


def digest(value):
    return hashlib.sha256(canonical(value)).hexdigest()


def source_claims(source):
    source_metadata(source)
    if not isinstance(source.get("path"),str) or not source["path"]:
        raise ValueError("Source location must be a nonempty string")
    return {k:deepcopy(v) for k,v in source.items() if k!="path"}


def create_template(analysis):
    analysis=validate_analysis(analysis)
    envelope=analysis["candidate_windows"]
    if envelope["status"]!="analyzed":
        raise ValueError("Candidate windows have not been analyzed")
    claims=source_claims(analysis["source_video"])
    check_provenance(envelope["provenance"],claims)
    windows=[(row["start"],row["end"]) for row in envelope["data"]]
    if len(set(windows))!=len(windows):
        raise ValueError("Duplicate candidate windows are ambiguous for human evaluation")
    provenance=envelope["provenance"]
    score_key=SCORE_KEYS.get(provenance.get("detector")) if (
        provenance.get("variant")=="fixed" and provenance.get("representation","selected_windows")
        in ("selected_windows","candidate_pool")) else None
    records=[]
    for index,row in enumerate(envelope["data"]):
        score=row.get(score_key) if score_key else None
        comparable=(type(score) in (int,float) and
                    row.get("detector",provenance.get("detector"))==provenance.get("detector"))
        records.append(dict(candidate_index=index,candidate_id=digest(dict(source=claims,candidate=row)),
            start=row["start"],end=row["end"],original_candidate=deepcopy(row),
            original_score_key=score_key,original_score=score if comparable else None,
            score_comparable=comparable,human_rating=None))
    binding=dict(analysis_schema_version=analysis["schema_version"],source_claims=claims,
                 candidate_windows=envelope)
    return dict(schema_version=1,artifact_type="highlight-ratings",
        analysis_schema_version=analysis["schema_version"],source_video=deepcopy(analysis["source_video"]),
        source_identity_status="reported_sha256_unverified" if "sha256" in claims else "unverified_missing_source_digest",
        candidate_provenance=deepcopy(provenance),candidate_set_sha256=digest(binding),
        rating_scale=deepcopy(SCALE),candidates=records)


def validate_ratings(analysis, ratings):
    expected=create_template(analysis)
    try:
        json_value(ratings)
        if not isinstance(ratings,dict) or set(ratings)!=set(expected):
            raise ValueError("Invalid rating template fields")
        actual=deepcopy(ratings)
        if not isinstance(actual["candidates"],list) or len(actual["candidates"])!=len(expected["candidates"]):
            raise ValueError("Rating candidate count mismatch")
        for row in actual["candidates"]:
            rating=row["human_rating"]
            if rating is not None and (type(rating) is not int or not 1<=rating<=5):
                raise ValueError("Human ratings must be integers 1–5 or null")
            row["human_rating"]=None
        # Location is informational; all content claims, candidates and provenance bind.
        actual["source_video"]=source_claims(actual["source_video"])
        expected["source_video"]=source_claims(expected["source_video"])
        if canonical(actual)!=canonical(expected):
            raise ValueError("Rating template mismatch: identity, candidates, order, scores or metadata changed")
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed rating template") from exc
    return ratings


def ordered_groups(rows,key):
    """Descending values with explicit tie groups; preserve input order within ties."""
    values=sorted({row[key] for row in rows},reverse=True)
    return [[row["candidate_index"] for row in rows if row[key]==value] for value in values]


def evaluate_ratings(analysis,ratings,evidence=None):
    validate_ratings(analysis,ratings)
    rows=deepcopy(ratings["candidates"])
    rated=[row for row in rows if row["human_rating"] is not None]
    pair_counts=dict.fromkeys(("agree","disagree","original_tie","human_tie","both_tied","incomparable","unrated"),0)
    pairs=[]
    disagreements={row["candidate_index"]:[] for row in rows}
    for first,second in combinations(rows,2):
        if first["human_rating"] is None or second["human_rating"] is None:
            status="unrated"
        elif not first["score_comparable"] or not second["score_comparable"]:
            status="incomparable"
        else:
            score_sign=(first["original_score"]>second["original_score"])-(first["original_score"]<second["original_score"])
            human_sign=(first["human_rating"]>second["human_rating"])-(first["human_rating"]<second["human_rating"])
            if score_sign==0 and human_sign==0: status="both_tied"
            elif score_sign==0: status="original_tie"
            elif human_sign==0: status="human_tie"
            else: status="agree" if score_sign==human_sign else "disagree"
        pair_counts[status]+=1
        pairs.append(dict(candidate_indices=[first["candidate_index"],second["candidate_index"]],status=status))
        if status=="disagree":
            disagreements[first["candidate_index"]].append(second["candidate_index"])
            disagreements[second["candidate_index"]].append(first["candidate_index"])
    for row in rows:
        row["disagrees_with_candidate_indices"]=disagreements[row["candidate_index"]]
    denominator=pair_counts["agree"]+pair_counts["disagree"]
    evidence_context=None
    if evidence is not None:
        validate_evidence(evidence)
        supplied=evidence["inputs"]["candidates"]
        if (canonical(source_claims(supplied["source_video"]))!=canonical(source_claims(analysis["source_video"]))
                or canonical(supplied["provenance"])!=canonical(analysis["candidate_windows"]["provenance"])
                or canonical([r["candidate"] for r in evidence["candidates"]])!=canonical(analysis["candidate_windows"]["data"])):
            raise ValueError("Optional evidence does not match the analysis candidates/source")
        evidence_context=dict(inputs=deepcopy(evidence["inputs"]),identity_comparison=evidence["identity_comparison"],
            candidates=[{k:deepcopy(row[k]) for k in ("candidate_index","matched_event_count","counts_by_modality","evidence_coverage")}
                        for row in evidence["candidates"]])
    return dict(schema_version=1,artifact_type="highlight-evaluation",
        input_provenance=dict(analysis_schema_version=analysis["schema_version"],
            candidate_set_sha256=ratings["candidate_set_sha256"],ratings_content_sha256=digest(ratings),
            candidate_provenance=deepcopy(ratings["candidate_provenance"])),
        source_video=deepcopy(analysis["source_video"]),source_identity_status=ratings["source_identity_status"],
        candidates=rows,metrics=dict(total_candidates=len(rows),rated=len(rated),unrated=len(rows)-len(rated),
            mean_human_rating=sum(row["human_rating"] for row in rated)/len(rated) if rated else None,
            original_candidate_order=[row["candidate_index"] for row in rows],
            human_preferred_order=ordered_groups(rated,"human_rating"),
            original_score_order=ordered_groups([row for row in rows if row["score_comparable"]],"original_score"),
            pair_counts=pair_counts,strict_pair_count=denominator,
            pairwise_agreement=pair_counts["agree"]/denominator if denominator else None),
        pairs=pairs,evidence_context=evidence_context,limitations=list(LIMITATIONS))


def publish(result,output,inputs,overwrite=False):
    output=Path(output)
    if output.is_symlink() or any(output.resolve()==Path(path).resolve() or
            output.exists() and Path(path).exists() and output.samefile(path) for path in inputs):
        raise ValueError("Output must not replace an input or symlink")
    if output.resolve().is_relative_to(ROOT) and not output.resolve().is_relative_to(ROOT/"output"):
        raise ValueError("Repository output must be under ignored output/")
    if output.exists() and overwrite:
        prior=read_json(output)
        if (not isinstance(prior,dict) or type(prior.get("schema_version")) is not int or
                prior["schema_version"]!=1 or prior.get("artifact_type")!=result["artifact_type"]):
            raise ValueError("Refusing to overwrite an unrelated artifact")
    save_query(result,output,overwrite)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    commands=parser.add_subparsers(dest="command",required=True)
    for name in ("template","evaluate"):
        command=commands.add_parser(name)
        command.add_argument("--analysis",type=Path,required=True)
        command.add_argument("--output",type=Path,required=True)
        command.add_argument("--overwrite",action="store_true")
        if name=="evaluate":
            command.add_argument("--ratings",type=Path,required=True)
            command.add_argument("--evidence",type=Path)
    args=parser.parse_args(argv)
    try:
        analysis=read_json(args.analysis)
        inputs=[args.analysis]
        if args.command=="template":
            result=create_template(analysis)
        else:
            inputs.append(args.ratings)
            evidence=read_json(args.evidence) if args.evidence else None
            if args.evidence:
                inputs.append(args.evidence)
            result=evaluate_ratings(analysis,read_json(args.ratings),evidence)
        publish(result,args.output,inputs,args.overwrite)
    except (OSError,ValueError) as exc:
        print(f"FAIL: highlight evaluation: {exc}",file=sys.stderr)
        return 1
    print(f"Saved {args.output}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
