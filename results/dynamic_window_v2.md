# Dynamic Windows V2: joint audio and scene boundaries

First-shot experiment on one already-edited Minecraft BedWars video (231.433288s), 14 unchanged human intervals. Candidates and recomputed Fixed/V1 metrics were checked against both frozen reports. Neither prior report was modified.

## Parameters frozen before evaluation

- Search each side from 4 to 20 seconds away, at 1-second steps; maximum total 40s, minimum 8s.
- At boundary b compare audio samples floor(b)-5 through floor(b)-1 with floor(b) through floor(b)+4. Use existing normalized audio scores floored at zero. Complete five-sample regions are required.
- Inward region is toward the candidate; outward is away. Require inward mean > 0 and outward mean <= 0.60 * inward mean. A regional reduction allows brief internal dips.
- Also require an existing normalized scene intensity >= 0.50 within +/-1s. Both conditions must coincide; select the nearest qualifying grid boundary independently on each side. No new scene detection or detector score changes.
- No qualifying boundary: use candidate-10 on the left or candidate+5 on the right, clamped to video bounds. Missing audio or scenes cannot establish a boundary. Minimum padding is symmetric and shifted inside the video; shorter videos use available duration.
- The 20s search gives longer context than V1; five-second means seek sustained reductions. The 40% reduction and half-max scene threshold are unvalidated first-shot choices. No labels or retention enter boundary generation; no parameters changed after evaluation.

## Three-way results

Mean/median include unmatched zeros. IoU >= 0.5 is an experimental reporting threshold, not a validated cutoff. Coverage is union-covered annotated time / annotated-union duration. Deltas use unrounded values; coverage differences are percentage points.

| Detector | K | Metric | Fixed | V1 | V2 | V2-Fixed | V2-V1 |
|---|---:|---|---:|---:|---:|---:|---:|
| Audio-only | 5 | Mean IoU | 0.543695 | 0.381090 | 0.543695 | +0.000000 | +0.162604 |
| Audio-only | 5 | Median IoU | 0.600000 | 0.347826 | 0.600000 | +0.000000 | +0.252174 |
| Audio-only | 5 | IoU >= 0.5 count | 3 | 1 | 3 | +0 | +2 |
| Audio-only | 5 | Coverage (%) | 32.547422 | 17.358625 | 32.547422 | +0.000000 pp | +15.188797 pp |
| Audio-only | 10 | Mean IoU | 0.465128 | 0.320124 | 0.508878 | +0.043750 | +0.188755 |
| Audio-only | 10 | Median IoU | 0.425725 | 0.276190 | 0.425725 | +0.000000 | +0.149534 |
| Audio-only | 10 | IoU >= 0.5 count | 4 | 1 | 4 | +0 | +3 |
| Audio-only | 10 | Coverage (%) | 64.660878 | 34.283284 | 67.264671 | +2.603794 pp | +32.981387 pp |
| Audio + Scene | 5 | Mean IoU | 0.517504 | 0.377916 | 0.517504 | +0.000000 | +0.139588 |
| Audio + Scene | 5 | Median IoU | 0.600000 | 0.347826 | 0.600000 | +0.000000 | +0.252174 |
| Audio + Scene | 5 | IoU >= 0.5 count | 3 | 1 | 3 | +0 | +2 |
| Audio + Scene | 5 | Coverage (%) | 32.547422 | 17.358625 | 32.547422 | +0.000000 pp | +15.188797 pp |
| Audio + Scene | 10 | Mean IoU | 0.465128 | 0.320124 | 0.508878 | +0.043750 | +0.188755 |
| Audio + Scene | 10 | Median IoU | 0.425725 | 0.276190 | 0.425725 | +0.000000 | +0.149534 |
| Audio + Scene | 10 | IoU >= 0.5 count | 4 | 1 | 4 | +0 | +3 |
| Audio + Scene | 10 | Coverage (%) | 64.660878 | 34.283284 | 67.264671 | +2.603794 pp | +32.981387 pp |
| Audio + Motion | 5 | Mean IoU | 0.509891 | 0.349135 | 0.509891 | +0.000000 | +0.160756 |
| Audio + Motion | 5 | Median IoU | 0.536862 | 0.347826 | 0.536862 | +0.000000 | +0.189036 |
| Audio + Motion | 5 | IoU >= 0.5 count | 3 | 0 | 3 | +0 | +3 |
| Audio + Motion | 5 | Coverage (%) | 30.565501 | 17.358500 | 30.565501 | +0.000000 pp | +13.207001 pp |
| Audio + Motion | 10 | Mean IoU | 0.477886 | 0.320121 | 0.521636 | +0.043750 | +0.201515 |
| Audio + Motion | 10 | Median IoU | 0.467391 | 0.276190 | 0.485822 | +0.018431 | +0.209632 |
| Audio + Motion | 10 | IoU >= 0.5 count | 5 | 1 | 5 | +0 | +4 |
| Audio + Motion | 10 | Coverage (%) | 62.678957 | 34.283159 | 65.282750 | +2.603794 pp | +30.999591 pp |

## Audio-only - Top 5

Candidate timestamps: 40, 69, 84, 146, 170

Side decisions (10 total): fallback_no_joint_boundary=5, fallback_no_strong_scene=5

| Candidate | V2 start/end | Duration | Backward reason | Forward reason | Minimum padded |
|---:|---|---:|---|---|---|
| 40 | 30.000000-45.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_joint_boundary | False |
| 69 | 59.000000-74.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 84 | 74.000000-89.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 146 | 136.000000-151.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 170 | 160.000000-175.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |

Accepted boundary evidence:

None; both sides use fallback for every candidate.

| GT start/end | Type | Fixed covered s | V1 covered s | V2 covered s | V2 coverage |
|---|---|---:|---:|---:|---:|
| 0-18 | intro | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 19-27 | transition | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 27-33 | combat | 3.000000 | 0.000000 | 3.000000 | 50.000000% |
| 33-47 | combat | 12.000000 | 8.000000 | 12.000000 | 85.714286% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 53-76 | combat | 17.000000 | 8.000000 | 17.000000 | 73.913043% |
| 76-85 | combat | 9.000000 | 5.500000 | 9.000000 | 100.000000% |
| 85-92 | victory | 4.000000 | 2.500000 | 4.000000 | 57.142857% |
| 92-122 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 122-158 | combat | 15.000000 | 8.000000 | 15.000000 | 41.666667% |
| 158-164 | transition | 4.000000 | 0.000000 | 4.000000 | 66.666667% |
| 164-192 | combat | 11.000000 | 8.000000 | 11.000000 | 39.285714% |
| 192-212 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 212-231.433 | victory | 0.000000 | 0.000000 | 0.000000 | 0.000000% |

## Audio-only - Top 10

Candidate timestamps: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217

Side decisions (20 total): audio_and_scene=2, fallback_no_joint_boundary=5, fallback_no_strong_scene=13

| Candidate | V2 start/end | Duration | Backward reason | Forward reason | Minimum padded |
|---:|---|---:|---|---|---|
| 18 | 8.000000-23.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 40 | 30.000000-45.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_joint_boundary | False |
| 69 | 59.000000-74.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 84 | 74.000000-89.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 103 | 91.000000-123.000000 | 32.000000 | audio_and_scene | audio_and_scene | False |
| 122 | 112.000000-127.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 146 | 136.000000-151.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 170 | 160.000000-175.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 192 | 182.000000-197.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 217 | 207.000000-222.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |

Accepted boundary evidence:

- 103s backward: boundary 91.000000s; inward/outward means 0.428930/0.220952; scene 90.550000s, intensity 1.000000.
- 103s forward: boundary 123.000000s; inward/outward means 0.484114/0.192586; scene 123.216667s, intensity 0.537581.

| GT start/end | Type | Fixed covered s | V1 covered s | V2 covered s | V2 coverage |
|---|---|---:|---:|---:|---:|
| 0-18 | intro | 10.000000 | 4.000000 | 10.000000 | 55.555556% |
| 19-27 | transition | 4.000000 | 3.000000 | 4.000000 | 50.000000% |
| 27-33 | combat | 3.000000 | 0.000000 | 3.000000 | 50.000000% |
| 33-47 | combat | 12.000000 | 8.000000 | 12.000000 | 85.714286% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 53-76 | combat | 17.000000 | 8.000000 | 17.000000 | 73.913043% |
| 76-85 | combat | 9.000000 | 5.500000 | 9.000000 | 100.000000% |
| 85-92 | victory | 4.000000 | 2.500000 | 5.000000 | 71.428571% |
| 92-122 | combat | 25.000000 | 14.500000 | 30.000000 | 100.000000% |
| 122-158 | combat | 20.000000 | 9.500000 | 20.000000 | 55.555556% |
| 158-164 | transition | 4.000000 | 0.000000 | 4.000000 | 66.666667% |
| 164-192 | combat | 21.000000 | 13.500000 | 21.000000 | 75.000000% |
| 192-212 | combat | 10.000000 | 2.500000 | 10.000000 | 50.000000% |
| 212-231.433 | victory | 10.000000 | 8.000000 | 10.000000 | 51.458859% |

## Audio + Scene - Top 5

Candidate timestamps: 40, 69, 84, 122, 170

Side decisions (10 total): fallback_no_joint_boundary=5, fallback_no_strong_scene=5

| Candidate | V2 start/end | Duration | Backward reason | Forward reason | Minimum padded |
|---:|---|---:|---|---|---|
| 40 | 30.000000-45.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_joint_boundary | False |
| 69 | 59.000000-74.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 84 | 74.000000-89.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 122 | 112.000000-127.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 170 | 160.000000-175.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |

Accepted boundary evidence:

None; both sides use fallback for every candidate.

| GT start/end | Type | Fixed covered s | V1 covered s | V2 covered s | V2 coverage |
|---|---|---:|---:|---:|---:|
| 0-18 | intro | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 19-27 | transition | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 27-33 | combat | 3.000000 | 0.000000 | 3.000000 | 50.000000% |
| 33-47 | combat | 12.000000 | 8.000000 | 12.000000 | 85.714286% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 53-76 | combat | 17.000000 | 8.000000 | 17.000000 | 73.913043% |
| 76-85 | combat | 9.000000 | 5.500000 | 9.000000 | 100.000000% |
| 85-92 | victory | 4.000000 | 2.500000 | 4.000000 | 57.142857% |
| 92-122 | combat | 10.000000 | 6.500000 | 10.000000 | 33.333333% |
| 122-158 | combat | 5.000000 | 1.500000 | 5.000000 | 13.888889% |
| 158-164 | transition | 4.000000 | 0.000000 | 4.000000 | 66.666667% |
| 164-192 | combat | 11.000000 | 8.000000 | 11.000000 | 39.285714% |
| 192-212 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 212-231.433 | victory | 0.000000 | 0.000000 | 0.000000 | 0.000000% |

## Audio + Scene - Top 10

Candidate timestamps: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217

Side decisions (20 total): audio_and_scene=2, fallback_no_joint_boundary=5, fallback_no_strong_scene=13

| Candidate | V2 start/end | Duration | Backward reason | Forward reason | Minimum padded |
|---:|---|---:|---|---|---|
| 18 | 8.000000-23.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 40 | 30.000000-45.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_joint_boundary | False |
| 69 | 59.000000-74.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 84 | 74.000000-89.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 103 | 91.000000-123.000000 | 32.000000 | audio_and_scene | audio_and_scene | False |
| 122 | 112.000000-127.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 146 | 136.000000-151.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 170 | 160.000000-175.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 192 | 182.000000-197.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 217 | 207.000000-222.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |

Accepted boundary evidence:

- 103s backward: boundary 91.000000s; inward/outward means 0.428930/0.220952; scene 90.550000s, intensity 1.000000.
- 103s forward: boundary 123.000000s; inward/outward means 0.484114/0.192586; scene 123.216667s, intensity 0.537581.

| GT start/end | Type | Fixed covered s | V1 covered s | V2 covered s | V2 coverage |
|---|---|---:|---:|---:|---:|
| 0-18 | intro | 10.000000 | 4.000000 | 10.000000 | 55.555556% |
| 19-27 | transition | 4.000000 | 3.000000 | 4.000000 | 50.000000% |
| 27-33 | combat | 3.000000 | 0.000000 | 3.000000 | 50.000000% |
| 33-47 | combat | 12.000000 | 8.000000 | 12.000000 | 85.714286% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 53-76 | combat | 17.000000 | 8.000000 | 17.000000 | 73.913043% |
| 76-85 | combat | 9.000000 | 5.500000 | 9.000000 | 100.000000% |
| 85-92 | victory | 4.000000 | 2.500000 | 5.000000 | 71.428571% |
| 92-122 | combat | 25.000000 | 14.500000 | 30.000000 | 100.000000% |
| 122-158 | combat | 20.000000 | 9.500000 | 20.000000 | 55.555556% |
| 158-164 | transition | 4.000000 | 0.000000 | 4.000000 | 66.666667% |
| 164-192 | combat | 21.000000 | 13.500000 | 21.000000 | 75.000000% |
| 192-212 | combat | 10.000000 | 2.500000 | 10.000000 | 50.000000% |
| 212-231.433 | victory | 10.000000 | 8.000000 | 10.000000 | 51.458859% |

## Audio + Motion - Top 5

Candidate timestamps: 69, 84, 146, 170, 231

Side decisions (10 total): fallback_insufficient_audio_context=1, fallback_no_joint_boundary=4, fallback_no_strong_scene=5

| Candidate | V2 start/end | Duration | Backward reason | Forward reason | Minimum padded |
|---:|---|---:|---|---|---|
| 69 | 59.000000-74.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 84 | 74.000000-89.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 146 | 136.000000-151.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 170 | 160.000000-175.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 231 | 221.000000-231.433288 | 10.433288 | fallback_no_strong_scene | fallback_insufficient_audio_context | False |

Accepted boundary evidence:

None; both sides use fallback for every candidate.

| GT start/end | Type | Fixed covered s | V1 covered s | V2 covered s | V2 coverage |
|---|---|---:|---:|---:|---:|
| 0-18 | intro | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 19-27 | transition | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 27-33 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 33-47 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 53-76 | combat | 17.000000 | 8.000000 | 17.000000 | 73.913043% |
| 76-85 | combat | 9.000000 | 5.500000 | 9.000000 | 100.000000% |
| 85-92 | victory | 4.000000 | 2.500000 | 4.000000 | 57.142857% |
| 92-122 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 122-158 | combat | 15.000000 | 8.000000 | 15.000000 | 41.666667% |
| 158-164 | transition | 4.000000 | 0.000000 | 4.000000 | 66.666667% |
| 164-192 | combat | 11.000000 | 8.000000 | 11.000000 | 39.285714% |
| 192-212 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 212-231.433 | victory | 10.433000 | 7.999712 | 10.433000 | 53.687027% |

## Audio + Motion - Top 10

Candidate timestamps: 18, 40, 69, 84, 103, 122, 146, 170, 192, 231

Side decisions (20 total): audio_and_scene=2, fallback_insufficient_audio_context=1, fallback_no_joint_boundary=5, fallback_no_strong_scene=12

| Candidate | V2 start/end | Duration | Backward reason | Forward reason | Minimum padded |
|---:|---|---:|---|---|---|
| 18 | 8.000000-23.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 40 | 30.000000-45.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_joint_boundary | False |
| 69 | 59.000000-74.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 84 | 74.000000-89.000000 | 15.000000 | fallback_no_joint_boundary | fallback_no_joint_boundary | False |
| 103 | 91.000000-123.000000 | 32.000000 | audio_and_scene | audio_and_scene | False |
| 122 | 112.000000-127.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 146 | 136.000000-151.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 170 | 160.000000-175.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 192 | 182.000000-197.000000 | 15.000000 | fallback_no_strong_scene | fallback_no_strong_scene | False |
| 231 | 221.000000-231.433288 | 10.433288 | fallback_no_strong_scene | fallback_insufficient_audio_context | False |

Accepted boundary evidence:

- 103s backward: boundary 91.000000s; inward/outward means 0.428930/0.220952; scene 90.550000s, intensity 1.000000.
- 103s forward: boundary 123.000000s; inward/outward means 0.484114/0.192586; scene 123.216667s, intensity 0.537581.

| GT start/end | Type | Fixed covered s | V1 covered s | V2 covered s | V2 coverage |
|---|---|---:|---:|---:|---:|
| 0-18 | intro | 10.000000 | 4.000000 | 10.000000 | 55.555556% |
| 19-27 | transition | 4.000000 | 3.000000 | 4.000000 | 50.000000% |
| 27-33 | combat | 3.000000 | 0.000000 | 3.000000 | 50.000000% |
| 33-47 | combat | 12.000000 | 8.000000 | 12.000000 | 85.714286% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.000000 | 0.000000% |
| 53-76 | combat | 17.000000 | 8.000000 | 17.000000 | 73.913043% |
| 76-85 | combat | 9.000000 | 5.500000 | 9.000000 | 100.000000% |
| 85-92 | victory | 4.000000 | 2.500000 | 5.000000 | 71.428571% |
| 92-122 | combat | 25.000000 | 14.500000 | 30.000000 | 100.000000% |
| 122-158 | combat | 20.000000 | 9.500000 | 20.000000 | 55.555556% |
| 158-164 | transition | 4.000000 | 0.000000 | 4.000000 | 66.666667% |
| 164-192 | combat | 21.000000 | 13.500000 | 21.000000 | 75.000000% |
| 192-212 | combat | 5.000000 | 2.500000 | 5.000000 | 25.000000% |
| 212-231.433 | victory | 10.433000 | 7.999712 | 10.433000 | 53.687027% |

## Fallback and limitations

Across 11 unique candidates (22 sides): audio_and_scene=2, fallback_insufficient_audio_context=1, fallback_no_joint_boundary=5, fallback_no_strong_scene=14

Repeated candidates across detector/K configurations are not independent observations. Audio/scene coincidences need not be semantic transitions. Regional averaging can miss boundaries; fallback equality is not evidence that the hypothesis works. Coverage depends on window duration. This single edited video cannot establish generalization or an overall winner.

Run: python evaluate_dynamic_windows_v2.py after tests. The unchanged main.py regenerates normal production clips; no V2 clips are generated. Full search evidence and metrics: output/dynamic_window_v2.json (ignored). Previous reports stay frozen.

## SHA-256 provenance

- results/fixed_window_v2_baseline.md: 93f141736c8a8a9da2575a7f5efcc4b61ceaff72ec48e8f2710d36050c16bab4
- results/dynamic_window_v1.md: b568475174b85093d2815b0ab8e919e46a3f92d571cb9f054b33f71b769356c0
- main.py: 379abfef0b75860feb2f642aa02a53f650a90dbf6ce18d082cdd63a0aa583f4e
- motion.py: 932da2a0839cae1d440e6fa4b895a242c619cbc318686ee05943c5d0650e5d9d
- evaluation.py: 2e0a83a392fb9ce8c64b00447a4981fc9e9da781977bd469de13e976cafe73fc
- evaluation_v2.py: 35acac250ad02ce12b8159554cc42b95468b776b96e4d8f94cdf35a3f372da16
- windows.py: 43f080b8beae53ef54c46e816b68bea4267d1497f822b3a1b33a178c81d9230b
- dynamic_windows.py: abd38b0cebc498893e6a9c78ed2c88133ca2cfdd8a7ff89f8a2e50e5b200c73b
- dynamic_windows_v2.py: cce875a9d303be83024664882dc28ae458f778b495ed80a6807c08779b517dc6
- evaluate_dynamic_windows_v2.py: 64b668883b441f47639fd3e3a09790c589703e6f812fb2facfae212753745834
- ground_truth_v2.json: 2fbf544b7994454bcc43dab93b1bf1295a45cec7055de6405762258f6694a8a1
- videos/my_recording.mp4: 6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09
