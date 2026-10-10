# Transcript Language Scoring V1: BedWars development run

One already-edited 231.433288-second Minecraft BedWars video; 19 saved ASR segments.
These are subjective text-model judgments, not calibrated probabilities, ground truth
or objective humor/content quality. No annotation/retention evidence was supplied.

## Model and setup

- Model: Qwen/Qwen2.5-1.5B-Instruct
- Exact revision: 989aa7980e4cf806f80c7fef2b1adb7bc71aa306
- Ryzen 9 270, 8 cores/16 threads, 16 GB RAM; RTX 5060 8 GB present but unused.
- Transformers 4.57.6; PyTorch 2.13.0; CPU/float32, four threads.
- Existing libraries reused read-only; no dependency installations or CUDA changes.
- Greedy decoding; maximum 160 new tokens, one previous/next speech segment.
- Exact system/user prompts and raw responses are retained in the analysis artifact.
- Prompt source: language_scoring.py; contract language-v1, default Minecraft topic.

## Output-contract development smoke

- Three synthetic segments: 3 valid, 0 invalid, 0 inference errors.
- Setup including download: 59.41 s; inference: 82.68 s.
- Initial prompt/chat-template/parser worked structurally; no prompt or interface repairs.
- Oversized-integer rejection was hardened by a mocked test; valid output behavior unchanged.
- Smoke success validates format only. Clearly surprised speech received reaction 0,
  while ordinary intro speech received 0.7. No ground-truth-based tuning followed.

## Real run

- Model setup: 9.75 s (cached weights).
- Target inference: 516.60 s.
- Total stage processing: 541.50 s.
- 19 scored; 0 invalid_output; 0 inference_error. Complete means structural success.

| Seconds | Transcript excerpt | Relevance | Humor | Reaction | Narrative context |
|---|---|---:|---:|---:|---:|
| 0.00-6.48 | The best Bedwars 16x texture packs for 1.8.9 that I think will give you an FPS boost. | 0.75 | 0.00 | 0.25 | 0.00 |
| 6.48-10.64 | I think you guys will really like these packs so make sure you stay tuned till the end and if you | 0.75 | 0.25 | 0.25 | 0.25 |
| 10.64-14.88 | like any make sure to comment what you appreciate that way I can know what type of packs you guys | 0.90 | 0.20 | 0.30 | 0.40 |
| 14.88-22.00 | want to see in the future. The first pack is Sleepless 16x. The helmet is pretty cool. | 0.90 | 0.20 | 0.70 | 0.80 |
| 22.00-30.72 | Oh wait is that a shark? Oh I love this pack. It's even color nice and vibrant. It looks so good. | 0.90 | 0.20 | 0.70 | 0.80 |
| 31.60-42.21 | I do not. Ah oh wait nice. Oh bet I love the bed break it's so clean. | 0.90 | 0.20 | 0.70 | 0.80 |
| 44.35-52.90 | Oh come here shark number two. Nice got the bed you want to play you want to play the exploding | 0.90 | 0.20 | 0.70 | 0.80 |
| 52.90-63.79 | fireball again. Oh oh I had to get him. Wow oh my gosh he's scaling this so fast. | 0.90 | 0.20 | 0.80 | 0.70 |
| 67.63-78.78 | Oh my goodness gracious everybody run. Oh become oh oh my gosh he has insane health. | 0.90 | 0.80 | 0.70 | 0.60 |
| 78.78-87.01 | I can't stop that joke. Ah I will let you kill me boy. I think he quit. | 0.90 | 0.20 | 0.70 | 0.80 |
| 90.46-96.86 | Isn't I call 16x? Oh wait he's up there. He fell into the void I guess. | 0.90 | 0.20 | 0.70 | 0.80 |
| 100.96-107.79 | Nice okay we slapped his body. I go down here and grab a bunch of this stuff. | 0.90 | 0.20 | 0.70 | 0.80 |
| 112.58-123.02 | Nice okay let's get the uh quick thinking combo. | 0.90 | 0.20 | 0.70 | 0.80 |
| 127.54-131.94 | You did it to me. Imagine if you got somebody's fireballs when you killed them. That would be just | 0.90 | 0.20 | 0.70 | 0.80 |
| 131.94-159.97 | a stupid broken. Oh frick. Wait how did I hit him? Bro this guy's annoying. This pack was highly | 0.90 | 0.20 | 0.70 | 0.80 |
| 159.97-166.45 | requested. It's venom 16x even got its own sound pack. That's that's like really nice. So hello | 0.90 | 0.20 | 0.70 | 0.80 |
| 166.45-187.01 | star. No it always works. Why? Dude really? Oh my gosh his body is about to get exploded. | 0.90 | 0.50 | 0.80 | 0.70 |
| 192.69-212.80 | Oh the fact that he's afk half the time. Yeah oh yeah. That's what I call a nice slappy. | 0.90 | 0.20 | 0.70 | 0.80 |
| 217.42-231.25 | Oh get him get him. Okay it was laggy a little bit. Oh oh. | 0.90 | 0.20 | 0.70 | 0.80 |

## Examples of higher model-assigned scores

These examples describe model outputs, not endorsements of content quality.

### relevance

- 10.64-14.88: 0.90; like any make sure to comment what you appreciate that way I can know what type of packs you guys
- 14.88-22.00: 0.90; want to see in the future. The first pack is Sleepless 16x. The helmet is pretty cool.
- 22.00-30.72: 0.90; Oh wait is that a shark? Oh I love this pack. It's even color nice and vibrant. It looks so good.

### humor

- 67.63-78.78: 0.80; Oh my goodness gracious everybody run. Oh become oh oh my gosh he has insane health.
- 166.45-187.01: 0.50; star. No it always works. Why? Dude really? Oh my gosh his body is about to get exploded.
- 6.48-10.64: 0.25; I think you guys will really like these packs so make sure you stay tuned till the end and if you

### reaction

- 52.90-63.79: 0.80; fireball again. Oh oh I had to get him. Wow oh my gosh he's scaling this so fast.
- 166.45-187.01: 0.80; star. No it always works. Why? Dude really? Oh my gosh his body is about to get exploded.
- 14.88-22.00: 0.70; want to see in the future. The first pack is Sleepless 16x. The helmet is pretty cool.

### narrative_context

- 14.88-22.00: 0.80; want to see in the future. The first pack is Sleepless 16x. The helmet is pretty cool.
- 22.00-30.72: 0.80; Oh wait is that a shark? Oh I love this pack. It's even color nice and vibrant. It looks so good.
- 31.60-42.21: 0.80; I do not. Ah oh wait nice. Oh bet I love the bed break it's so clean.

## Questionable judgments and limits

- 13/19 segments received the identical tuple (0.9, 0.2, 0.7, 0.8) in relevance/humor/reaction/narrative order.
- The opening topic/setup explanation received narrative_context 0, despite explanatory text.
- 'Everybody run ... insane health' received humor 0.8; the text alone does not establish a joke.
- The third-highest humor output is only 0.25 for 'stay tuned'; it is a relative example, not strong humor.
- Relevance is usually 0.9. This run provides little separation between most segments.
- The model may confuse target and neighbor context; ASR errors and sentence fragmentation
  introduce further ambiguity. Vocal tone and visual meaning are absent.
- No repeatability/calibration/human-agreement study was performed; valid JSON is not
  evidence of accurate contextual interpretation. No ranking or assembly was changed.

## Preservation and verification

- Every non-language field matches the pre-run loaded artifact, including transcript text,
  timestamps/provenance, source, visual/acoustic evidence, events and candidate windows.
- Real cache hit verified with a backend that would raise if called; saved bytes unchanged.
- Deterministic shared save/load serialization verified.
- Baseline: 179 unittest tests plus four motion checks passed.
- Final: 204 unittest tests plus four motion checks passed.
- New tests use mocked inference, including failures, strict parsing, cache/force,
  missing/empty speech, provenance, versioning, legacy compatibility and atomic/concurrent preservation.
- Frozen detectors, ground truth, retention, weights, boundaries and clipping remain unchanged.
- No commit or push.

Artifacts (ignored output directory): output/shared_analysis_v1.json,
output/language_smoke_v1.json and output/shared_analysis_before_language.json.
