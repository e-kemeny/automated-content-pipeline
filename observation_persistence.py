"""Opt-in persistence of actual audio/scene detector outputs; no clip generation."""
import argparse
import contextlib
from copy import deepcopy
from fractions import Fraction
import hashlib
import io
import json
from pathlib import Path
import subprocess
import sys
import tempfile

import main as producers
from media_probe import probe_format_streams
from source_identity import file_identity, validate_identity
from transcription import extract_audio
from multimodal_timeline import (audio_events, scene_events, json_value, number, read_json,
                                 reconcile, sort_key, validate_timeline, save_timeline)
from timeline_query import save_query

ROOT = Path(__file__).resolve().parent
AUDIO_PROVENANCE = dict(producer="main.analyze_audio", version=1,
    cadence_seconds=1, baseline_intervals=5, first_scored_second=5,
    amplitude_units="mean absolute signed-16-bit PCM sample amplitude",
    spike_units="PCM sample amplitude difference",
    score_units="PCM sample amplitude; current amplitude + spike",
    amplitude_coverage="all decoded audio chunks, including a partial final chunk",
    score_coverage="all chunks after five baseline chunks; not peak-filtered",
    output_order="amplitudes chronological; scores descending with stable ties",
    temporal_coverage="unknown outside decoded audio")
SCENE_PROVENANCE = dict(producer="main.analyze_video_motion", version=1,
    filter="scdet=t=10", threshold=10, score_units="FFmpeg lavfi.scd.score",
    cadence="input frames; only producer-parsed emitted scene changes retained",
    output_order="descending score with stable ties", detector_output="complete",
    temporal_coverage="sparse detected events; not dense frame-comparison measurements")
UNANALYZED = ["transcript", "motion", "semantic_events", "language"]


def validate_observations(artifact):
    try:
        json_value(artifact)
        if (set(artifact) != {"schema_version","artifact_type","source_video","source_identity",
                             "audio","scene_changes","unanalyzed_modalities","producer_sha256"}
                or type(artifact["schema_version"]) is not int or artifact["schema_version"] != 1
                or artifact["artifact_type"] != "full-observations"):
            raise ValueError("Unsupported full observation artifact")
        identity = validate_identity(artifact["source_identity"])
        source = artifact["source_video"]
        expected = dict(identity["media"], sha256=identity["digest"],size_bytes=identity["size_bytes"])
        if {k:v for k,v in source.items() if k != "path"} != expected or not isinstance(source["path"],str):
            raise ValueError("Source metadata disagrees with content identity")
        digest=artifact["producer_sha256"]
        if not isinstance(digest,str) or len(digest)!=64 or any(c not in "0123456789abcdef" for c in digest):
            raise ValueError("Invalid producer code digest")
        if artifact["unanalyzed_modalities"] != UNANALYZED:
            raise ValueError("Invalid unanalyzed modality declaration")
        audio, scenes = artifact["audio"], artifact["scene_changes"]
        if (audio["status"] != "analyzed" or scenes["status"] != "analyzed"
                or audio["provenance"] != AUDIO_PROVENANCE or scenes["provenance"] != SCENE_PROVENANCE):
            raise ValueError("Invalid detector status/provenance")
        if type(audio["sample_count"]) is not int or audio["sample_count"] < 0:
            raise ValueError("Invalid decoded sample count")
        if type(audio["sample_rate_hz"]) is not int or audio["sample_rate_hz"] != 16000 or type(audio["channels"]) is not int or audio["channels"] != 1:
            raise ValueError("Expected mono 16 kHz audio")
        duration=identity["media"]["duration_seconds"]
        for name,time_key,values in (("amplitude_rows","second",("volume",)),("score_rows","second",("spike","score"))):
            rows=audio[name]
            if not isinstance(rows,list):
                raise ValueError("Audio rows must be a list")
            for row in rows:
                if type(row[time_key]) is not int or not 0 <= row[time_key] <= duration:
                    raise ValueError("Invalid audio timestamp")
                for key in values:
                    number(row[key])
                if name=="amplitude_rows" and row["volume"]<0:
                    raise ValueError("Negative mean absolute amplitude")
            key=(lambda row:row["second"]) if name=="amplitude_rows" else (lambda row:-row["score"])
            if rows != sorted(rows,key=key):
                raise ValueError("Original audio ordering invalid")
        chunks=(audio["sample_count"]+audio["sample_rate_hz"]-1)//audio["sample_rate_hz"]
        if [r["second"] for r in audio["amplitude_rows"]] != list(range(chunks)) or sorted(r["second"] for r in audio["score_rows"]) != list(range(5,chunks)):
            raise ValueError("Audio rows do not cover all producer chunks")
        if not isinstance(scenes["data"],list):
            raise ValueError("Scene rows must be a list")
        for row in scenes["data"]:
            if not 0 <= number(row["time"]) <= duration or number(row["score"])<0:
                raise ValueError("Invalid scene observation")
        if scenes["data"] != sorted(scenes["data"],key=lambda row:-row["score"]):
            raise ValueError("Original scene ordering invalid")
        return artifact
    except (KeyError,TypeError,AttributeError) as exc:
        raise ValueError("Malformed full observation artifact") from exc


def stat_identity(path):
    s=path.stat()
    return (s.st_dev,s.st_ino,s.st_size,s.st_mtime_ns,s.st_ctime_ns)


def collect_observations(video):
    """One hash, one probe, one audio extraction and one scene pass."""
    video=Path(video)
    if video.is_symlink() or not video.is_file():
        raise ValueError("Source must be an existing regular non-symlink video")
    video=video.resolve()
    before=stat_identity(video)
    digest,size=file_identity(video)
    metadata=probe_format_streams(video)
    try:
        streams=metadata["streams"]
        stream=next(s for s in streams if s["codec_type"]=="video")
        if not any(s["codec_type"]=="audio" for s in streams):
            raise ValueError("Video has no audio stream")
        media=dict(duration_seconds=float(metadata["format"]["duration"]),
                   width=stream["width"],height=stream["height"])
        fps=Fraction(stream.get("avg_frame_rate","0/1"))
        if fps>0:
            media["fps"]=float(fps)
    except (KeyError,TypeError,StopIteration,ZeroDivisionError) as exc:
        raise ValueError("Invalid video metadata") from exc
    identity=validate_identity(dict(version=1,algorithm="sha256",digest=digest,size_bytes=size,media=media))
    captured={}
    with tempfile.TemporaryDirectory(prefix="observation-audio-") as directory:
        wav=Path(directory)/"audio.wav"
        extract_audio(video,wav)
        # Preserve legacy producer prints for normal callers; this CLI stays concise.
        with contextlib.redirect_stdout(io.StringIO()):
            scores=producers.analyze_audio(wav,observation_sink=captured.update)
            scenes=producers.analyze_video_motion(video,check=True)
    if video.is_symlink() or stat_identity(video)!=before:
        raise ValueError("Source changed during analysis")
    artifact=dict(schema_version=1,artifact_type="full-observations",
        source_video=dict(path=str(video),sha256=digest,size_bytes=size,**media),
        source_identity=identity,
        producer_sha256=hashlib.sha256(Path(producers.__file__).read_bytes()).hexdigest(),
        audio=dict(status="analyzed",amplitude_rows=captured["volumes"],score_rows=scores,
                   sample_rate_hz=captured["sample_rate"],channels=captured["channels"],
                   sample_count=captured["sample_count"],provenance=deepcopy(AUDIO_PROVENANCE)),
        scene_changes=dict(status="analyzed",data=scenes,provenance=deepcopy(SCENE_PROVENANCE)),
        unanalyzed_modalities=list(UNANALYZED))
    return validate_observations(artifact)


def to_timeline(artifact, reference="full-observations"):
    """Normalize persisted rows only; never analyze media again."""
    validate_observations(artifact)
    audio=artifact["audio"]
    channels={
        "audio_activity":dict(status="analyzed",provenance=dict(audio["provenance"],
            producer_sha256=artifact["producer_sha256"],original_artifact=reference)),
        "scene_changes":dict(status="analyzed",provenance=dict(artifact["scene_changes"]["provenance"],
            producer_sha256=artifact["producer_sha256"],original_artifact=reference))}
    source=dict(kind="analysis",artifact=reference,source_video=deepcopy(artifact["source_video"]),channels=channels)
    events=[]
    for channel, rows, adapter in (
            ("audio_activity",audio["amplitude_rows"]+audio["score_rows"],audio_events),
            ("scene_changes",artifact["scene_changes"]["data"],scene_events)):
        observations=adapter(rows,dict(artifact_index=0,channel=channel,provenance=deepcopy(channels[channel]["provenance"])))
        for row in observations:
            row["source_order"]=len(events)
            events.append(row)
    return validate_timeline(dict(schema_version=1,timeline_type="multimodal-observations",
        sources=[source],events=sorted(events,key=sort_key),**reconcile([source])))


def check_destination(output, source, overwrite, timeline=False):
    output,source=Path(output),Path(source)
    if output.is_symlink() or output.resolve()==source.resolve() or (
            output.exists() and source.exists() and output.samefile(source)):
        raise ValueError("Output must not replace a source or symlink")
    if output.resolve().is_relative_to(ROOT) and not output.resolve().is_relative_to(ROOT/"output"):
        raise ValueError("Repository output must be under ignored output/")
    if output.exists():
        if not overwrite:
            raise FileExistsError("Output exists; use --overwrite")
        (validate_timeline if timeline else validate_observations)(read_json(output))


def main(argv=None):
    parser=argparse.ArgumentParser(description=__doc__)
    inputs=parser.add_mutually_exclusive_group(required=True)
    inputs.add_argument("--video",type=Path)
    inputs.add_argument("--timeline-from",type=Path,help="Normalize a saved full-observation artifact without processing media")
    parser.add_argument("--output",type=Path,required=True)
    parser.add_argument("--overwrite",action="store_true")
    args=parser.parse_args(argv)
    source=args.video or args.timeline_from
    try:
        check_destination(args.output,source,args.overwrite,timeline=args.timeline_from is not None)
        if args.video:
            artifact=collect_observations(args.video)
            check_destination(args.output,source,args.overwrite)
            save_query(artifact,args.output,args.overwrite)
        else:
            artifact=to_timeline(read_json(args.timeline_from),str(args.timeline_from))
            save_timeline(artifact,args.output,args.overwrite)
    except (OSError,ValueError,subprocess.SubprocessError) as exc:
        print(f"FAIL: observation persistence: {exc}",file=sys.stderr)
        return 1
    print(f"Saved {args.output}")
    return 0


if __name__=="__main__":
    raise SystemExit(main())
