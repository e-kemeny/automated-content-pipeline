"""Score only persisted transcript language signals; never rerun other analysis."""
import argparse
import json
import os
from pathlib import Path
import tempfile
import time

from shared_analysis import LANGUAGE_SIGNALS, load_analysis, save_analysis
from language_scoring import (LocalTextModel, apply_results, contract, fingerprint,
    score_segments, smoke_test)


def atomic_save(analysis, path):
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".language_", suffix=".json", delete=False) as handle:
        temporary = Path(handle.name)
    try:
        save_analysis(analysis, temporary)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def update_language(path, *, force=False, factory=LocalTextModel, require_smoke=True):
    path = Path(path)
    original_bytes = path.read_bytes()
    analysis = load_analysis(path)
    if analysis["transcript"]["status"] != "analyzed":
        raise ValueError("Transcript has not been analyzed")
    segments = analysis["transcript"]["data"]
    signature = fingerprint(dict(contract=contract(), transcript=segments))
    existing = list(analysis["language"].values())
    attempted = any(s["status"] != "not_analyzed" for s in existing)
    if attempted and not force:
        if all(s["provenance"].get("input_signature") == signature for s in existing):
            return analysis, True  # Failed attempts also remain inspectable until explicit force.
        raise ValueError("Existing language signals differ from this transcript/contract; use --force")
    if segments and require_smoke:
        smoke_path = path.parent/"language_smoke_v1.json"
        smoke = json.loads(smoke_path.read_text(encoding="utf-8"))
        if smoke.get("contract") != contract() or smoke.get("passed") is not True:
            raise ValueError("Run a passing --smoke test for this contract before full scoring")
    started = time.perf_counter()
    provenance = dict(contract(), input_signature=signature)
    if segments:
        try:
            backend = factory(path.parent/"language_model_cache")
        except Exception as exc:
            reason = f"{type(exc).__name__}: {exc}"
            def unavailable(prompt):
                raise RuntimeError(reason)
            backend = unavailable
            provenance["setup_error"] = reason
        else:
            provenance.update(backend.provenance)
        results = score_segments(segments, backend)
    else:
        results = []  # No model initialization for analyzed silence.
    provenance["processing_seconds"] = time.perf_counter()-started
    provenance["inference_seconds"] = sum(r["inference_seconds"] for r in results)
    updated = apply_results(analysis, results, provenance)
    if path.read_bytes() != original_bytes:
        raise RuntimeError("Analysis changed during scoring; refusing to overwrite other stages")
    atomic_save(updated, path)
    return updated, False


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--analysis", type=Path, required=True)
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--smoke", action="store_true", help="Check synthetic output contract; do not update analysis")
    args = parser.parse_args(argv)
    try:
        if args.smoke:
            load_analysis(args.analysis)
            backend = LocalTextModel(args.analysis.parent/"language_model_cache")
            report = smoke_test(backend)
            report["provenance"] = backend.provenance
            report["inference_seconds"] = sum(r["inference_seconds"] for r in report["results"])
            path = args.analysis.parent/"language_smoke_v1.json"
            path.write_text(json.dumps(report, indent=2, sort_keys=True, allow_nan=False)+"\n", encoding="utf-8")
            print(f"Smoke passed: {report['passed']}; report: {path}")
            if not report["passed"]:
                return 1
        else:
            analysis, reused = update_language(args.analysis, force=args.force)
            print(f"{'Reused' if reused else 'Saved'} language signals")
            print(analysis["language"]["relevance"]["provenance"]["counts"])
            if analysis["language"]["relevance"]["status"] == "failed":
                return 1
    except (ValueError, RuntimeError, OSError) as exc:
        parser.exit(1, f"Language scoring failed: {exc}\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
