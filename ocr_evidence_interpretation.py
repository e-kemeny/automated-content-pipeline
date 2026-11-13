"""Experimental phrase hypotheses over saved OCR JSON; no OCR or event detection."""
import argparse
from copy import deepcopy
from fractions import Fraction
from pathlib import Path
import re
import sys

from highlight_evaluation import digest, publish
from multimodal_timeline import json_value, number, read_json
from ocr_visual_evidence import validate_result
from source_identity import validate_identity


PROFILE_PATHS = {
    name: Path(__file__).resolve().parent / "profiles" / f"ocr_interpretation_{name}_v1.json"
    for name in ("generic", "bedwars")
}


def default_profile(game="generic"):
    """Unknown game names explicitly fall back to generic; no game inference."""
    if not isinstance(game, str) or not game.strip():
        raise ValueError("Game must be a nonempty string")
    return read_json(PROFILE_PATHS.get(game, PROFILE_PATHS["generic"]))


def validate_profile(profile):
    json_value(profile)
    if (not isinstance(profile, dict) or set(profile) != {"schema_version", "name", "patterns"}
            or type(profile["schema_version"]) is not int or profile["schema_version"] != 1
            or not isinstance(profile["name"], str) or not profile["name"].strip()
            or not isinstance(profile["patterns"], list)):
        raise ValueError("Invalid phrase profile")
    ids = set()
    for pattern in profile["patterns"]:
        if (not isinstance(pattern, dict) or set(pattern) != {"id", "event_type", "phrase"}
                or any(not isinstance(v, str) or not v.strip() for v in pattern.values())
                or pattern["id"] in ids):
            raise ValueError("Patterns require unique IDs and nonempty literal phrases")
        ids.add(pattern["id"])
    return deepcopy(profile)


def validate_evidence(evidence):
    """Validate fields consumed here; retain other producer fields without reinterpretation."""
    json_value(evidence)
    try:
        if (type(evidence["schema_version"]) is not int or evidence["schema_version"] != 1
                or evidence["artifact_type"] != "ocr-visual-evidence"):
            raise ValueError("Unsupported OCR evidence schema")
        duration = validate_identity(evidence["source_identity"])["media"]["duration_seconds"]
        if (not isinstance(evidence["backend"], dict)
                or not isinstance(evidence["visual_evidence_provenance"], dict)
                or not isinstance(evidence["observations"], list)):
            raise ValueError("Missing OCR provenance/observations")
        previous, ids = -1, set()
        for row in evidence["observations"]:
            for key in ("observation_id", "parent_frame_id"):
                if not isinstance(row[key], str) or not row[key]:
                    raise ValueError("Missing observation/frame identity")
            if row["observation_id"] in ids:
                raise ValueError("Duplicate observation ID")
            ids.add(row["observation_id"])
            if row["kind"] not in ("full", "crop"):
                raise ValueError("Invalid observation kind")
            if row["kind"] == "crop" and (not isinstance(row["region_name"], str) or not row["region_name"]):
                raise ValueError("Missing crop region identity")
            stamp = row["timestamp"]
            second = number(stamp["timestamp_seconds"])
            pts, base = stamp["normalized_pts"], stamp["time_base"]
            if (type(pts) is not int or pts < 0 or not isinstance(base, str)
                    or not re.fullmatch(r"\d+(?:/\d+)?", base)):
                raise ValueError("Invalid measured timestamp")
            time_base = Fraction(base)
            if time_base <= 0 or second != float(pts*time_base) or not 0 <= second <= duration or second < previous:
                raise ValueError("Invalid timestamp bounds/order")
            previous = second
            status = row["status"]
            if status in ("text_found", "no_text"):
                image = row["image"]
                if any(type(image[k]) is not int or image[k] <= 0 for k in ("width", "height")):
                    raise ValueError("Invalid image dimensions")
                validate_result(dict(text=row["text"], words=row["words"]), image["width"], image["height"])
                if (status == "text_found") != bool(row["text"].strip()):
                    raise ValueError("OCR status disagrees with text")
            elif status in ("unavailable", "failed"):
                if row["text"] is not None or row["words"] is not None:
                    raise ValueError("Failed/unavailable OCR must not supply recognized text")
            else:
                raise ValueError("Unsupported OCR status")
    except (KeyError, TypeError, AttributeError, ZeroDivisionError) as exc:
        raise ValueError("Malformed OCR evidence") from exc


def interpret_evidence(evidence, *, game="generic", profile=None):
    """Retain observations in source order; equal timestamps (full/crop) are allowed."""
    if profile is not None and game != "generic":
        raise ValueError("Choose a game or a custom profile, not both")
    chosen = validate_profile(default_profile(game) if profile is None else profile)
    compiled = [
        (p, re.compile(r"(?<!\w)" + r"\s+".join(re.escape(w) for w in p["phrase"].split()) + r"(?!\w)", re.IGNORECASE))
        for p in chosen["patterns"]
    ]
    if evidence is not None:
        validate_evidence(evidence)
    rows = [] if evidence is None else evidence["observations"]
    interpretations = []
    for row in rows:
        hypotheses = []
        if row["status"] == "text_found":
            for pattern, expression in compiled:
                for match in expression.finditer(row["text"]):
                    hypotheses.append(dict(
                        status="hypothesis", pattern_id=pattern["id"],
                        event_type=pattern["event_type"], matched_text=match.group(),
                        text_span=[match.start(), match.end()]))
            hypotheses.sort(key=lambda h: (h["text_span"][0], h["text_span"][1], h["pattern_id"]))
        status = ("ocr_unavailable" if row["status"] == "unavailable" else
                  "ocr_failed" if row["status"] == "failed" else
                  "no_text" if row["status"] == "no_text" else
                  "hypotheses" if hypotheses else "no_match")
        interpretations.append(dict(observation_id=row["observation_id"], status=status, hypotheses=hypotheses))
    return dict(
        schema_version=1, artifact_type="ocr-evidence-interpretation",
        status="not_analyzed" if evidence is None else "no_observations" if not rows else "interpreted",
        input_evidence=deepcopy(evidence), input_evidence_digest=None if evidence is None else digest(evidence),
        profile=chosen, requested_game=game if profile is None else None,
        unknown_game_fallback=profile is None and game not in ("generic", "bedwars"),
        interpretations=interpretations,
        limitations=[
            "Literal phrase matches are hypotheses, not confirmed gameplay events or contextual understanding.",
            "Negation, chat, tutorials, quotations and OCR errors can produce false positives.",
            "No match or missing OCR is not evidence that gameplay events were absent.",
            "Input identity, images, timestamps and confidence are preserved claims, not independently verified here.",
            "Word confidence is OCR confidence, not hypothesis confidence. No event score is calculated.",
            "Full-frame/crop/repeated observations are retained independently; no deduplication or event timing inference.",
        ])


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    group = parser.add_mutually_exclusive_group()
    group.add_argument("--game", default="generic")
    group.add_argument("--profile", type=Path)
    args = parser.parse_args(argv)
    try:
        evidence = read_json(args.input)
        result = interpret_evidence(evidence, game=args.game,
                                    profile=read_json(args.profile) if args.profile else None)
        publish(result, args.output, [args.input] + ([args.profile] if args.profile else []))
        print(f"Saved {args.output}: {len(result['interpretations'])} observations; hypotheses only")
        return 0
    except (OSError, ValueError) as exc:
        print(f"FAIL: OCR interpretation: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
