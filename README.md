# Gameplay Content Pipeline

A Python engineering project for detecting and clipping gameplay highlights, with short-form processing and publishing planned.

> 🚧 **In Development**

## Overview

Gameplay Content Pipeline is being built incrementally toward an automated workflow from gameplay footage to edited content. Current work focuses on signal-based highlight ranking, automatic clip generation, and human-labeled evaluation.

## Current Progress

- Portable file handling with `pathlib` and video duration probing with ffprobe.
- FFmpeg-based mono 16 kHz audio extraction and per-second audio activity/spike scoring against a rolling five-second baseline.
- FFmpeg scene-change detection and normalized multimodal ranking with experimental **70% audio / 30% visual** weighting. Each audio candidate uses the strongest nearby visual evidence within ±5 seconds.
- Greedy score-ranked selection with **15-second minimum separation** to suppress redundant highlights, followed by chronological output.
- Automatic Audio + Scene clip generation: 10 seconds before each selected event and 5 seconds after, clamped to video bounds.
- Human-labeled Top-5 and Top-10 evaluation, diagnostic clips for error analysis, and a terminal tool for human interval annotations.
- Planned: short-form processing and automated publishing.

## Experimental Evaluation

The V1 harness matches predicted timestamps to human labels with ±5-second tolerance and one match per ground-truth event, reporting precision, recall, and F1. Both cutoffs use the same greedy selection rules.

An evaluation-only motion experiment samples **5 FPS at 160×90 grayscale**, measures mean absolute consecutive-frame difference, and averages it per second. Maximum-normalized motion replaces scene evidence in a separate Audio + Motion ranking, using the same association window and 70/30 weighting. Production clips still use Audio + Scene.

| Detector | Top-5 F1 | Top-10 F1 |
|---|---:|---:|
| Audio-only | 0.3333 | 0.4348 |
| Audio + Scene | 0.3333 | 0.4348 |
| Audio + Motion | 0.2222 | 0.4348 |

**Motion did not improve the baseline:** Top-5 F1 fell and Top-10 F1 tied. These experimental results come from **one already-edited Minecraft BedWars video**; they do not establish generalization. The detectors are signal-based heuristics, not a trained ML model.

## Current Research Direction

Human error analysis revealed that point timestamps poorly represented longer gameplay sequences worth retaining. Ground Truth V2 represents these as human-labeled time intervals with semantic types: `intro`, `transition`, `combat`, `objective`, `victory`, and `other`. Objectives can include meaningful events such as bed breaks.

The annotation workflow exists; V1 evaluation remains unchanged. The next stage is investigating interval-based evaluation and viewer-retention data before adding another detector signal.

## Tech Stack

- Python
- FFmpeg / ffprobe

## Project Structure

```text
gameplay-content-pipeline/
├── main.py                 # Pipeline and experiment comparison
├── evaluation.py           # V1 selection and evaluation
├── motion.py               # Experimental visual activity signal
├── error_analysis.py       # Diagnostic clips for human review
├── annotate.py             # Interactive V2 interval annotation
├── ground_truth_v2.json    # Human-entered intervals
├── videos/                 # Local source media (Git-ignored)
├── output/                 # Generated artifacts (Git-ignored)
├── requirements.txt
└── README.md
```
