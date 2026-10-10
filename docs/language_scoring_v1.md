# Transcript-Based Language Scoring V1

This optional stage reads the existing analyzed transcript and writes four
independent language signals to the same Shared Analysis document used by
future Shorts and Long-form consumers. It performs no other inference.

## Model and runtime

Pinned model: Qwen/Qwen2.5-1.5B-Instruct, revision
989aa7980e4cf806f80c7fef2b1adb7bc71aa306.
Official model card: https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct

The development machine has an AMD Ryzen 9 270 (8 cores/16 threads), 16 GB RAM,
and an RTX 5060 with 8 GB VRAM. Installed PyTorch 2.13.0 is CPU-only, so this
stage explicitly uses CPU/float32, four threads, Transformers 4.57.6.
No CUDA fallback, quantization, training or API service is involved.
The existing output/clip_env libraries were reused read-only: no CLIP or VLM
model is loaded. requirements-language.txt describes an optional separate
environment; existing experiment requirements are unchanged.

From the repository root:

    output/clip_env/Scripts/python.exe score_language.py --analysis output/shared_analysis_v1.json --smoke
    output/clip_env/Scripts/python.exe score_language.py --analysis output/shared_analysis_v1.json

A separate environment can instead install requirements-language.txt and use
its interpreter. Standard-library unit tests do not need model dependencies.
The initial download is approximately 3 GB; cached weights are reused locally.

## Prompt and output contract

The exact system prompt is SYSTEM_PROMPT in language_scoring.py and is copied
into each signal's provenance. Each user prompt is preserved in input_prompt.
The topic is explicitly Minecraft BedWars gameplay and texture packs; one
previous and one next segment supply speech context. Only the target is scored.
No annotation, retention, detector evidence or human judgment enters the prompt.

The model must produce one plain JSON object containing exactly relevance,
humor, reaction and narrative_context, independently scored from 0 to 1.
Relevance means relation to topic or neighboring speech; humor means an apparent
textual joke/funny observation; reaction means expressed strong response;
narrative_context means explanation/setup/transition/continuity.

Greedy decoding, maximum 160 new tokens; inputs above 4096 tokens fail instead
of being truncated. The tokenizer's native chat template is used. Parsing
rejects extra/missing/duplicate keys, markdown, explanations, strings, booleans,
nulls, nonfinite values and values outside [0,1]. Nothing is repaired or filled
with guessed scores. There are no inference retries or aggregate quality scores.

## Persistence, failures and reuse

Each language signal retains the existing status/data/provenance envelope.
Each target row contains original start/end/text, segment_index, score,
status, raw_output, failure_reason, input_prompt and inference_seconds.
Statuses are scored, invalid_output or inference_error. Failed scores are null.
One model response produces all four dimensions; judgments are not four passes.

The smallest additive Shared Analysis V1 extension permits partial and failed
envelope statuses only for language signals. Existing V1 documents and legacy
language rows remain valid. The loader checks per-row score validity and
completion consistency. All other signal validation is unchanged.

- not_analyzed: no attempt.
- analyzed + completion empty: analyzed transcript contains no segments; no model loaded.
- partial: at least one scored target and at least one failure.
- failed: every target failed; analysis is not marked complete.
- analyzed + completion complete: all targets structurally valid, not semantically validated.

A signature binds the full transcript and frozen scoring contract. Repeat calls
reuse the saved attempt without inference or rewriting. Successful scores stay
cached; failures remain inspectable and are not retried automatically.
Use --force to replace only language signals, including retrying failures.
Changed transcripts/contracts or pre-existing signals from another producer
require explicit force. Force never refreshes transcription or detectors.
Atomic deterministic saving preserves every other field after load/save.
Provenance retains model revision, library/device/dtype, prompt/options,
input signature, counts, setup and inference/processing times.

## Development smoke test and limitations

Before the real 19-segment run, three synthetic targets tested strict structured
output. All three parsed successfully with the initial prompt and parser; no
prompt/contract changes or label-based tuning were made. A numeric-validation
edge case for extremely large integers was hardened by a mocked test after
smoke testing; it does not alter valid responses. The smoke artifact is
output/language_smoke_v1.json and is required before scoring nonempty transcripts.
It is a structure test, not accuracy validation: the clearly emotional synthetic
"Oh wow! That explosion scared me!" received reaction 0, while ordinary intro
speech received 0.7. These questionable judgments are retained openly.

Scores are subjective ranking signals, not calibrated probabilities, verified
ground truth, objective humor or content quality. The small model can confuse
target/context, overrate routine speech, or repeat similar judgments. ASR
mistakes, clipped sentence segments, missing tone/visuals and one-neighbor
context further limit interpretation. CPU inference is a batch workflow.
Nothing feeds these signals into ranking, boundaries or video assembly.
