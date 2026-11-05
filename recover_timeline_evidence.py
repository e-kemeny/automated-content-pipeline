"""Opt-in recovery of sparse cached Dynamic V2 evidence; never runs analysis."""
import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys

from multimodal_timeline import (build_timeline, event, json_value, number, read_json,
                                 reconcile, save_timeline, sort_key, validate_timeline)


def recover_dynamic_v2(artifact, reference="dynamic-window-v2"):
    """Recover selected audio rows and diagnostic scene references, not full streams."""
    json_value(artifact)
    if not isinstance(reference, str) or not reference:
        raise ValueError("Artifact reference must be a nonempty string")
    if not isinstance(artifact, list) or not artifact:
        raise ValueError("Expected nonempty Dynamic V2 result list")
    channels = {
        "audio_activity": dict(status="analyzed", provenance=dict(
            recovery_adapter="dynamic-window-v2-recovery", recovery_version=1,
            basis="fixed.windows selected audio rows; incomplete selection-biased sample",
            original_artifact=reference, temporal_coverage="unknown")),
        "scene_changes": dict(status="analyzed", provenance=dict(
            recovery_adapter="dynamic-window-v2-recovery", recovery_version=1,
            basis="v2.windows boundary diagnostics; repeated strongest-nearby scene references",
            intensity="already normalized; raw scene intensity unavailable",
            original_artifact=reference, temporal_coverage="unknown")),
    }
    source = dict(kind="analysis", artifact=reference, source_video={}, channels=channels)
    events = []
    counts = dict.fromkeys(channels, 0)

    def add(payload, channel, event_type, key, pointer):
        src = dict(artifact_index=0, channel=channel,
                   provenance=deepcopy(channels[channel]["provenance"]), artifact_pointer=pointer)
        observation = event(payload, "audio" if channel=="audio_activity" else "visual",
                            event_type, key, None, src, counts[channel])
        observation["source_order"] = len(events)
        events.append(observation)
        counts[channel] += 1

    try:
        for i, pair in enumerate(artifact):
            if not isinstance(pair, dict) or set(pair) != {"fixed","v1","v2"}:
                raise ValueError("Unsupported Dynamic V2 pair fields; no inferred identity")
            fixed = pair["fixed"]
            if fixed["detector"] not in ("Audio-only","Audio + Scene","Audio + Motion"):
                raise ValueError("Unsupported cached detector")
            if type(fixed["k"]) is not int or fixed["k"] <= 0:
                raise ValueError("Invalid cached K")
            for variant in ("fixed","v1","v2"):
                if not isinstance(pair[variant]["windows"],list):
                    raise ValueError("Cached windows must be lists")
            for j, row in enumerate(fixed["windows"]):
                if not 0 <= number(row["start"]) <= number(row["second"]) <= number(row["end"]):
                    raise ValueError("Invalid original audio window")
                for key in ("spike","score","normalized_score"):
                    number(row[key])
                add(row,"audio_activity","audio_spike_score","second",f"/{i}/fixed/windows/{j}")
            for j, window in enumerate(pair["v2"]["windows"]):
                if not 0 <= number(window["start"]) <= number(window["end"]):
                    raise ValueError("Invalid V2 window")
                for side in ("backward","forward"):
                    diagnostics = window["boundary_diagnostics"][side]["evidence"]
                    if not isinstance(diagnostics,list):
                        raise ValueError("Boundary evidence must be a list")
                    for k, row in enumerate(diagnostics):
                        if set(row) != {"boundary","inward_mean","outward_mean","scene_time","scene_score","audio_ok","scene_ok"}:
                            raise ValueError("Unsupported boundary diagnostic")
                        if number(row["boundary"]) < 0:
                            raise ValueError("Invalid boundary timestamp")
                        for name in ("inward_mean","outward_mean"):
                            if row[name] is not None:
                                number(row[name])
                        if any(type(row[name]) is not bool for name in ("audio_ok","scene_ok")):
                            raise ValueError("Invalid diagnostic flags")
                        timestamp, score = row["scene_time"], row["scene_score"]
                        if timestamp is None and score is None:
                            continue  # No retained scene; never create a zero-valued event.
                        if number(timestamp) < 0 or not 0 <= number(score) <= 1:
                            raise ValueError("Invalid normalized scene reference")
                        payload = dict(time=timestamp, normalized_score=score,
                                       recovery_diagnostic=deepcopy(row))
                        add(payload,"scene_changes","scene_change","time",
                            f"/{i}/v2/windows/{j}/boundary_diagnostics/{side}/evidence/{k}")
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed Dynamic V2 cached result") from exc
    result = dict(schema_version=1,timeline_type="multimodal-observations",sources=[source],
                  events=sorted(events,key=sort_key),**reconcile([source]))
    return validate_timeline(result)


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--dynamic-v2",type=Path,help="Existing dynamic_window_v2.json")
    inputs.add_argument("--analysis",type=Path,help="Existing Shared Analysis V1; use its existing adapters")
    parser.add_argument("--output",type=Path)
    parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args(argv)
    if args.overwrite and args.output is None:
        parser.error("--overwrite requires --output")
    path=args.dynamic_v2 or args.analysis
    try:
        if args.output is not None and (args.output.resolve()==path.resolve() or
                args.output.exists() and path.exists() and args.output.samefile(path)):
            raise ValueError("Output must not replace input")
        data=read_json(path)
        result=(recover_dynamic_v2(data,str(path)) if args.dynamic_v2 else
                build_timeline(analysis=data,labels={"analysis":str(path)}))
        if args.output is not None:
            save_timeline(result,args.output,args.overwrite)
        print(json.dumps(result,separators=(",",":"),allow_nan=False))
    except (OSError,ValueError) as exc:
        print(f"FAIL: evidence recovery: {exc}",file=sys.stderr)
        return 1
    return 0


if __name__=="__main__":
    raise SystemExit(main())
