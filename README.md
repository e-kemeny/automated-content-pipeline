# Gameplay Content Pipeline

An automated pipeline for detecting, clipping, processing, and publishing gameplay highlights.

> 🚧 **In Development**

## Overview

Gameplay Content Pipeline is a Python-based system designed to automate the workflow between raw gameplay footage and published short-form content.

The project is being built incrementally, starting with reliable video processing and clipping before adding automated highlight detection and publishing.

## Current Progress

- [x] Portable file handling with `pathlib`
- [x] FFmpeg / ffprobe integration
- [x] Video metadata extraction
- [ ] Automated video clipping
- [ ] Highlight detection
- [ ] Video processing
- [ ] Automated publishing

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
