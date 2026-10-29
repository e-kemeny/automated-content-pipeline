# GPU vision inference V1 (optional experiment)

This isolated experiment checks whether pretrained image classification can run
on real video frames on the GPU desktop. It does not change production selection,
boundaries, shared analysis, or exports. Development and mocked testing remain
on the laptop; no real model inference or weight download was performed there.

## Model and environment

ResNet-18 is a small, established image-classification baseline with official
ImageNet weights and preprocessing. The experiment fixes
ResNet18_Weights.IMAGENET1K_V1 rather than a moving DEFAULT alias.
It uses the weight object's transforms and category names directly.
The [official torchvision model documentation](https://docs.pytorch.org/vision/stable/models/generated/torchvision.models.resnet18.html)
describes the resize, center crop and normalization for these weights.

The optional environment needs compatible CUDA-enabled PyTorch, torchvision and
Pillow, plus FFmpeg/FFprobe on PATH. Imports are lazy; ordinary tests use mocks.
No packages are installed by this script. Match torch/torchvision binary builds,
Python, GPU and driver using official installation guidance; the earlier RTX 4090
arithmetic result does not establish torchvision/model compatibility. No universal
dependency combination is claimed or added to the export requirements.

## Desktop commands

From the repository root, using the optional GPU environment:

    .\.venv-gpu\Scripts\python.exe vision_inference.py --video videos/my_recording.mp4
    .\.venv-gpu\Scripts\python.exe vision_inference.py --video videos/my_recording.mp4 --device cuda:0 --frames 5 --output output/vision_inference_v1.json
    # Explicit permission to obtain missing official weights:
    .\.venv-gpu\Scripts\python.exe vision_inference.py --video videos/my_recording.mp4 --allow-model-download
    # Replace only an existing JSON owned by this experiment:
    .\.venv-gpu\Scripts\python.exe vision_inference.py --video videos/my_recording.mp4 --overwrite

Without download permission, the script only reads the checkpoint at
torch.hub.get_dir()/checkpoints/<official-weight-filename>. It verifies the
filename's SHA-256 prefix and uses torch.load(weights_only=True, map_location="cpu")
from an open local handle. The model builder receives weights=None, then loads
this state dictionary: it cannot trigger an implicit model download.
Missing weights fail with instructions. A corrupt existing cache fails even
with download permission; it is not silently repaired. With permission and a
missing checkpoint, the official URL loader uses check_hash=True. Use a trusted
external torch cache (TORCH_HOME may select it); do not put weights in Git.
A short filename hash prefix is a corruption check, not a security signature.

## Frames, inference and measurements

Frame counts are bounded to 1-100 (default 5). For duration D and count N,
requested timestamps are D*i/(N+1), i=1..N. Endpoints are excluded.
The first non-attached-picture video stream is probed with the existing shared
FFprobe helper. Audio is not required. FFmpeg extracts one RGB PNG at each seek
into a private temporary directory; images and directory are removed afterward.
Frame extraction has a 60-second timeout. Unsupported/undecodable media fails.
Timestamps identify requested seek positions, not measured decoded-frame PTS;
variable frame rate and very short videos can yield nearby or repeated frames.

The model loads once, moves to the explicit CUDA device, enters eval mode and
runs under torch.inference_mode(). No CPU inference fallback exists.
Per-frame latency measures forward pass plus softmax, with CUDA synchronization
before and after; it excludes extraction, preprocessing, input transfer and
top-three CPU transfer. There is no warmup: the first frame can include lazy
initialization costs. These timings are observations, not a performance benchmark.

Peak allocated MiB is PyTorch's selected-device allocation peak reset before
model placement; it includes resident allocations and excludes memory reserved
but not allocated by PyTorch and other processes. Total elapsed seconds covers
validation, full source hashes, imports/loading/download if allowed, extraction
and inference through final source verification, excluding JSON publication.
No cross-hardware/version determinism claim is made.

## JSON and output safety

Schema version 1 has these fields (no fabricated example scores):

- schema_version, experiment (vision-inference-v1).
- video: path, full-file sha256, size_bytes, duration_seconds, width, height,
  stream_index. Existing source_identity.file_identity supplies stable-read
  hashing; content is rechecked after inference. Its existing contract is unchanged.
- sampling: method, frame_count, timestamps_are.
- model: name, weights identifier, weights_url.
- runtime: pytorch_version, torchvision_version, cuda_build_version, device,
  gpu_name, total_elapsed_seconds, peak_allocated_gpu_memory_mib.
- frames: timestamp_seconds, top3 (category/confidence), inference_latency_ms.

Confidence is ImageNet softmax probability, not calibrated gameplay correctness.
JSON keys are sorted, indented and finite; predictions/timings are not deterministic.
No JSON or destination directory is created until every frame and source recheck
succeeds. Output inside the checkout must be under ignored output/; other external
locations are permitted. Do not use a separately tracked external directory.
Existing unrelated JSON and symlink outputs are rejected, including with overwrite.

Publication uses a flushed temporary file in the destination directory.
--overwrite uses atomic replacement; default uses an atomic hard link so a
concurrently created destination is never clobbered, then removes the temporary
name. Filesystems without hard-link support fail rather than fall back to unsafe
replacement. Publication failure can leave a newly created empty output directory,
but no partial JSON. Concurrent --overwrite writers are unsupported; run one
experiment per destination. Native libraries/FFprobe have no overall watchdog;
temporary frame cleanup cannot be guaranteed after forcible process termination.

Exit 0 means complete JSON publication; runtime/validation failures return 1;
argument parsing errors return 2. No partial result is labeled successful.

## Interpretation and next steps

ImageNet categories describe photographs, not Minecraft events. Textures, HUDs,
stylized objects and center cropping can produce confident but irrelevant labels.
This does not detect fights, kills, objectives or narrative structure, and sparse
independent frames cannot establish temporal events. The experiment is GPU/model
plumbing, not production video understanding.

A later separately evaluated step can consider video-specific or gameplay semantic
models and temporal context. Do not turn these ImageNet scores into highlight
weights or treat them as ground truth. Actual desktop ResNet inference, latency,
memory and model compatibility remain unverified until the owner runs the CLI.

Tests:

    python -m unittest test_vision_inference -q
    python verify.py
