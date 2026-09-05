# Gameplay Content Pipeline

An automated pipeline for detecting, clipping, processing, and publishing gameplay highlights.

> 🚧 **In Development**

## Overview

Gameplay Content Pipeline is a Python-based system designed to automate the workflow between raw gameplay footage and published short-form content.

The project is being built incrementally, starting with reliable video processing and clipping, followed by audio-based highlight detection and eventually automated short-form processing and publishing.

## Current Progress

- ✅ Portable file handling with `pathlib`
- ✅ FFmpeg / ffprobe integration
- ✅ Video metadata and duration extraction
- ✅ Automated video clipping
- ✅ Audio extraction for analysis
- ✅ Per-second audio volume analysis
- ✅ Audio peak detection and ranking
- ✅ Duplicate/nearby peak filtering
- 🚧 Automatic highlight clip generation
- ⏳ Video processing for short-form content
- ⏳ Automated publishing

## Tech Stack

- Python
- FFmpeg / ffprobe

## Project Structure

```text
gameplay-content-pipeline/
├── main.py
├── videos/
├── output/
├── requirements.txt
└── README.md
