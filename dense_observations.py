"""CPU observation cache shared by future output modes; no selection or exports."""
import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import motion
import observation_persistence as persistence
from shared_analysis import validate_analysis
from source_identity import file_identity, canonical
from media_probe import probe_format_streams
from multimodal_timeline import number, read_json, event, sort_key, validate_timeline
from highlight_evaluation import digest, publish
from clip_boundary_experiment import match_source

ROOT=Path(__file__).resolve().parent
CLOCKS=dict(audio="decoded mono 16kHz WAV chunks, second zero at decoded audio start",
    motion="5 FPS resampled video with setpts=PTS-STARTPTS; later frame second; one-second averages",
    scene="existing FFmpeg scdet emitted lavfi.scd.time; producer values unchanged",
    visual="existing CLIP sampling timestamps and filter; labels are unconfirmed hypotheses")


def recipe():
    files=("dense_observations.py","observation_persistence.py","main.py","motion.py","transcription.py","media_probe.py")
    version=subprocess.run(["ffmpeg","-version"],check=True,capture_output=True,text=True,timeout=15).stdout.splitlines()[0]
    return dict(version=1,ffmpeg=version,producer_hashes={
        name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files})


def visual_input(analysis,source):
    if analysis is None:
        return dict(status="not_analyzed",data=[],provenance={})
    analysis=validate_analysis(analysis)
    match_source(analysis["source_video"],source)
    visual=deepcopy(analysis["visual"]["semantic_frames"])
    if visual["status"]=="analyzed":
        p=visual["provenance"]
        if p.get("video_sha256")!=source["sha256"] or p.get("duration")!=source["duration_seconds"]:
            raise ValueError("CLIP source provenance mismatch")
        if p.get("model_id")!="openai/clip-vit-base-patch32" or not p.get("model_revision"):
            raise ValueError("Only existing source-bound CLIP frame observations supported")
        if any("timestamp" not in r for r in visual["data"]):
            raise ValueError("Expected sampled point observations, not semantic intervals")
    return visual


def changes(rows,time_key,value_key):
    return [dict(second=r[time_key],change=r[value_key]-rows[i-1][value_key])
            for i,r in enumerate(rows) if i]


def build(full,motion_rows,visual,metadata,config):
    persistence.validate_observations(full)
    duration=full["source_identity"]["media"]["duration_seconds"]
    if not isinstance(motion_rows,list) or not motion_rows:
        raise ValueError("Motion producer returned no frames; no observations fabricated")
    if [r["second"] for r in motion_rows]!=list(range(len(motion_rows))):
        raise ValueError("Motion bins must be contiguous and chronological")
    for row in motion_rows:
        if type(row["second"]) is not int or not 0<=row["second"]<=duration:
            raise ValueError("Invalid motion timestamp")
        if not 0<=number(row["score"])<=1 or not 0<=number(row["normalized_score"])<=1:
            raise ValueError("Invalid motion measurement")
    # Validate cached CLIP through existing analysis schema, including ordering/bounds.
    from shared_analysis import create_analysis
    check=create_analysis(full["source_video"])
    check["visual"]["semantic_frames"]=deepcopy(visual)
    visual_input(check,full["source_video"])
    amplitude=full["audio"]["amplitude_rows"]
    timeline=persistence.to_timeline(full,"dense/full_observations")
    channels=timeline["sources"][0]["channels"]
    for name,clock in (("audio_activity","audio"),("scene_changes","scene")):
        channels[name]["provenance"]["clock"]=CLOCKS[clock]
    for row in timeline["events"]:
        row["source"]["provenance"]=deepcopy(channels[row["source"]["channel"]]["provenance"])
    additions=[
        ("audio_changes","audio","audio_activity_change",changes(amplitude,"second","volume"),"second",
         dict(clock=CLOCKS["audio"],units="PCM amplitude difference",cadence_seconds=1)),
        ("motion","visual","motion_activity",motion_rows,"second",
         dict(clock=CLOCKS["motion"],sample_fps=5,width=160,height=90,pixel_format="gray",
              cadence_seconds=1,units="mean absolute consecutive-frame difference / 255",
              normalization="per-video maximum",first_frame="no predecessor; no contribution")),
        ("motion_changes","visual","motion_activity_change",changes(motion_rows,"second","score"),"second",
         dict(clock=CLOCKS["motion"],cadence_seconds=1,units="difference in raw one-second motion means")),
        ("frames","visual","clip_hypothesis",visual["data"],"timestamp",
         dict(visual["provenance"],clock=CLOCKS["visual"],confirmed_event=False))]
    for channel,modality,kind,rows,time_key,provenance in additions:
        channels[channel]=dict(status=visual["status"] if channel=="frames" else "analyzed",provenance=provenance)
        for i,row in enumerate(rows):
            e=event(row,modality,kind,time_key,None,
                    dict(artifact_index=0,channel=channel,provenance=deepcopy(provenance)),i)
            e["source_order"]=len(timeline["events"])
            timeline["events"].append(e)
    timeline["events"].sort(key=sort_key)
    validate_timeline(timeline)
    audio_seconds=full["audio"]["sample_count"]/full["audio"]["sample_rate_hz"]
    result=dict(schema_version=1,artifact_type="dense-observations",source_identity=deepcopy(full["source_identity"]),
        recipe=deepcopy(config),full_observations=deepcopy(full),motion_rows=deepcopy(motion_rows),
        visual=deepcopy(visual),stream_metadata=deepcopy(metadata),timeline=timeline,
        coverage=dict(audio=dict(count=len(amplitude),decoded_seconds=audio_seconds,cadence_seconds=1),
            audio_spikes=dict(count=len(full["audio"]["score_rows"]),first_scored_second=5),
            motion=dict(count=len(motion_rows),first_second=motion_rows[0]["second"],last_second=motion_rows[-1]["second"],
                        sampled_fps=5,aggregation_seconds=1,partial_final_bin=True),
            scene=dict(count=len(full["scene_changes"]["data"]),coverage="sparse thresholded discontinuities, not every frame"),
            visual=dict(status=visual["status"],count=len(visual["data"])),
            game_transitions=dict(status="unavailable",reason="Scene changes and CLIP hypotheses do not confirm game transitions"),
            ocr=dict(status="not_analyzed"),alignment="native clocks retained; cross-modal offset not independently verified"))
    result["content_sha256"]=digest(result)
    return result


def validate(artifact):
    try:
        expected=build(artifact["full_observations"],artifact["motion_rows"],artifact["visual"],
                       artifact["stream_metadata"],artifact["recipe"])
        if canonical(expected)!=canonical(artifact):
            raise ValueError("Dense cache content/schema mismatch")
        return artifact
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed dense cache") from exc


def collect(video,output,analysis=None):
    video,output=Path(video),Path(output)
    if video.is_symlink() or not video.is_file():
        raise ValueError("Missing regular source video")
    if output.is_symlink() or output.resolve()==video.resolve():
        raise ValueError("Unsafe cache destination")
    before=persistence.stat_identity(video)
    checksum,size=file_identity(video)
    config=recipe()
    if output.exists():
        cached=validate(read_json(output))
        identity=cached["source_identity"]
        if identity["digest"]!=checksum or identity["size_bytes"]!=size or cached["recipe"]!=config:
            raise ValueError("Stale cache: source or producer changed; use a new output path")
        source=cached["full_observations"]["source_video"]
        if canonical(visual_input(analysis,source))!=canonical(cached["visual"]):
            raise ValueError("Stale visual input; use a new output path")
        if persistence.stat_identity(video)!=before:
            raise ValueError("Source changed during cache verification")
        return cached,"reused"
    # Existing helper performs one audio extraction/analysis and one scene pass.
    full=persistence.collect_observations(video)
    if full["source_identity"]["digest"]!=checksum or full["source_identity"]["size_bytes"]!=size:
        raise ValueError("Source changed before collection")
    visual=visual_input(analysis,full["source_video"])
    metadata=probe_format_streams(video)
    streams=[{k:s[k] for k in ("index","codec_type","time_base","start_time","duration") if k in s}
             for s in metadata["streams"]]
    observed=motion.analyze_motion(video)
    if persistence.stat_identity(video)!=before:
        raise ValueError("Source changed during collection")
    result=build(full,observed,visual,streams,config)
    publish(result,output,[video])
    return result,"created"


def boundary_report(artifact,boundaries,radius=2):
    """Native-clock neighborhood diagnostics, not a score or chosen boundary."""
    validate(artifact)
    if number(radius)<=0:
        raise ValueError("Radius must be positive")
    duration=artifact["source_identity"]["media"]["duration_seconds"]
    result=[]
    audio=artifact["full_observations"]["audio"]["amplitude_rows"]
    motion_rows=artifact["motion_rows"]
    for t in boundaries:
        if not 0<=number(t)<=duration:raise ValueError("Boundary outside source")
        row=dict(second=t,radius=radius,alignment="native clocks; offsets unverified")
        for name,rows,key in (("audio",audio,"volume"),("motion",motion_rows,"score")):
            before=[r for r in rows if t-radius<=r["second"]<t]
            after=[r for r in rows if t<=r["second"]<=t+radius]
            mean_before=sum(r[key] for r in before)/len(before) if before else None
            mean_after=sum(r[key] for r in after)/len(after) if after else None
            row[name]=dict(before=deepcopy(before),after=deepcopy(after),
                mean_change=None if mean_before is None or mean_after is None else mean_after-mean_before,
                peak=max(before+after,key=lambda r:r[key]) if before or after else None)
        row["scene_changes"]=[deepcopy(r) for r in artifact["full_observations"]["scene_changes"]["data"] if abs(r["time"]-t)<=radius]
        result.append(row)
    return result


def main(argv=None):
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--video",type=Path,required=True)
    p.add_argument("--output",type=Path,required=True)
    p.add_argument("--analysis",type=Path,help="Reuse CLIP; report original candidate neighborhoods, no ranking")
    args=p.parse_args(argv)
    try:
        if args.analysis and args.output.resolve()==args.analysis.resolve():
            raise ValueError("Output cannot replace analysis")
        analysis=read_json(args.analysis) if args.analysis else None
        artifact,status=collect(args.video,args.output,analysis)
        summary=dict(cache=status,coverage=artifact["coverage"],source_identity=artifact["source_identity"])
        if analysis is not None:
            boundaries=sorted({r[k] for r in analysis["candidate_windows"]["data"] for k in ("start","end")})
            summary["boundary_neighborhoods"]=boundary_report(artifact,boundaries)
        print(json.dumps(summary,sort_keys=True,indent=2,allow_nan=False))
        return 0
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print("FAIL: dense observations: "+str(exc),file=sys.stderr)
        return 1


if __name__=="__main__":
    raise SystemExit(main())
