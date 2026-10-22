"""Portable manifest V2 identity; no migration or inference."""
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path


def canonical(value):
    """Canonical within this Python/JSON contract, not RFC 8785."""
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("utf-8")


def file_identity(path):
    """Full-file digest and byte count with best-effort stable-read detection."""
    path = Path(path)
    if path.is_symlink():
        raise ValueError("V2 source must not be a symlink")
    before = path.stat()
    digest = hashlib.sha256()
    count = 0
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            count += len(chunk)
            digest.update(chunk)
    after = path.stat()
    fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns", "st_ctime_ns")
    if path.is_symlink() or any(getattr(before,k) != getattr(after,k) for k in fields) or count != after.st_size:
        raise ValueError("V2 source changed while hashing")
    return digest.hexdigest(), count


def validate_identity(value):
    if not isinstance(value, dict) or set(value) != {"version","algorithm","digest","size_bytes","media"}:
        raise ValueError("Invalid V2 source identity fields")
    if type(value["version"]) is not int or value["version"] != 1 or value["algorithm"] != "sha256":
        raise ValueError("Unsupported V2 source identity version/algorithm")
    digest = value["digest"]
    if not isinstance(digest,str) or len(digest) != 64 or any(c not in "0123456789abcdef" for c in digest):
        raise ValueError("Invalid V2 source digest")
    if type(value["size_bytes"]) is not int or value["size_bytes"] < 0:
        raise ValueError("Invalid V2 source byte count")
    media = value["media"]
    if not isinstance(media,dict) or not {"duration_seconds","width","height"} <= set(media) or set(media)-{"duration_seconds","width","height","fps"}:
        raise ValueError("Invalid V2 media fields")
    for key, number in media.items():
        if type(number) not in (int,float) or not math.isfinite(number) or number <= 0:
            raise ValueError("Invalid V2 media metadata")
        if key in ("width","height") and type(number) is not int:
            raise ValueError("Invalid V2 dimensions")
    return value


def source_identity(path, source):
    digest, size = file_identity(path)
    if digest != source["sha256"]:
        raise ValueError("V2 source changed since probing")
    value = dict(version=1, algorithm="sha256", digest=digest, size_bytes=size,
                 media={k:source[k] for k in ("duration_seconds","width","height","fps") if k in source})
    return validate_identity(value)


def plan_signature(manifest):
    """Sign plan inputs, not runtime status, locators or encoded-file hashes."""
    payload = dict(domain="gameplay-export-plan-v2", exporter=manifest["exporter"],
        source_identity=manifest["source_identity"],
        shared_analysis={k:manifest["shared_analysis"][k] for k in ("schema_version","sha256")},
        encoding=manifest["encoding"])
    if manifest["exporter"] == "shorts-export-v1":
        payload["selection"] = manifest["selection"]
        payload["clips"] = [{k:r[k] for k in ("candidate_timestamp","start","end","duration",
            "ranking_score","ranking_score_key","candidate_evidence","output_filename")} for r in manifest["clips"]]
    elif manifest["exporter"] == "longform-export-v1":
        payload["planning"] = manifest["planning"]
    else:
        raise ValueError("Unknown V2 exporter")
    return hashlib.sha256(canonical(payload)).hexdigest()


def prepare_v2(video, directory, manifest, output_root, *, cache_only, dry_run, force):
    if force:
        raise ValueError("V2 creation does not support force; use a new isolated destination")
    if not cache_only:
        root = Path(output_root).resolve()
        default = Path("output").resolve()
        if root == default or root.is_relative_to(default):
            raise ValueError("V2 creation requires an isolated output root outside default output")
        if directory.exists() and (not directory.is_dir() or any(directory.iterdir())):
            raise ValueError("V2 creation requires an empty destination; no migration or replacement")
    result = deepcopy(manifest)
    result["manifest_version"] = 2
    result["source_identity"] = source_identity(video, manifest["source"])
    result["source_location"] = dict(recorded_path=str(video))
    # source remains a compatibility metadata view; path alone is informational.
    result["plan_signature"] = plan_signature(result)
    return result


def validate_manifest_identity(prior, expected):
    try:
        if type(prior.get("manifest_version")) is not int or prior["manifest_version"] != 2:
            raise ValueError("V2 cache requires manifest version 2; no automatic conversion")
        identity = validate_identity(prior["source_identity"])
        if identity != expected["source_identity"]:
            raise ValueError("V2 source content identity mismatch")
        source = prior["source"]
        if (not isinstance(source,dict) or
            {k:v for k,v in source.items() if k != "path"} !=
            dict(identity["media"], sha256=identity["digest"])):
            raise ValueError("V2 source metadata disagrees with identity")
        location = prior["source_location"]
        if not isinstance(location,dict) or set(location) != {"recorded_path"} or not isinstance(location["recorded_path"],str):
            raise ValueError("Invalid V2 source location")
        for key in ("exporter","encoding"):
            if prior.get(key) != expected[key]:
                raise ValueError(f"V2 stale {key}")
        for key in ("sha256","schema_version"):
            if prior["shared_analysis"][key] != expected["shared_analysis"][key]:
                raise ValueError("V2 stale shared analysis")
        if prior["plan_signature"] != plan_signature(prior) or prior["plan_signature"] != expected["plan_signature"]:
            raise ValueError("V2 stale or invalid plan signature")
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed V2 manifest") from exc


def verify_inputs(video, analysis_path, manifest):
    digest, size = file_identity(video)
    if (digest, size) != (manifest["source_identity"]["digest"],manifest["source_identity"]["size_bytes"]):
        raise ValueError("V2 source changed during operation")
    if hashlib.sha256(Path(analysis_path).read_bytes()).hexdigest() != manifest["shared_analysis"]["sha256"]:
        raise ValueError("V2 analysis changed during operation")
