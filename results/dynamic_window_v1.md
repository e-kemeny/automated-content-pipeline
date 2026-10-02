# Dynamic window V1: first-shot boundary experiment

One already-edited Minecraft BedWars video, 231.433288s; 14 unchanged V2 annotations.
Fixed results were recomputed and verified against `results/fixed_window_v2_baseline.md`, which was not modified. Every fixed/dynamic pair uses identical selected timestamps and score metadata.

## Algorithm frozen before evaluation

- Signal: existing per-second `normalized_score` from audio candidates, floored at zero. This is the existing volume-plus-spike score, not raw loudness; detector scores are unchanged.
- Resolution: 1s; sample at floor(time). Local baseline: median within +/-15s of the candidate.
- Quiet threshold = baseline + 0.25 * max(0, candidate activity - baseline). The relative rule seeks a return toward local activity; it is not a learned cutoff.
- Expand each side independently, at most 15s per side (30s total). Two consecutive samples <= threshold stop expansion at the inner edge of that quiet run. One quiet sample is bridged; missing signal stops at the last examined boundary.
- Minimum 8s retains brief context: pad symmetrically and shift padding inward at video edges. If the video is shorter, use its available duration. All windows contain their candidate and are clamped.
- The 30s cap bounds context, 1s steps match the existing signal, and two quiet samples avoid terminating on a single dip. Parameters were declared before V2 evaluation and were not tuned.
- No GT labels or retention enter boundary generation. Production clipping is unchanged; the runner reruns main.py once and regenerates its normal fixed clips only.

## Fixed versus dynamic

IoU >= 0.5 is an experimental reporting threshold, not a validated cutoff. Mean/median include unmatched zeros. Coverage uses unions of predicted and annotated time. Deltas are dynamic minus fixed; coverage deltas are percentage points.

| Detector | K | Metric | Fixed | Dynamic | Delta |
|---|---:|---|---:|---:|---:|
| Audio-only | 5 | Mean IoU | 0.543695 | 0.381090 | -0.162604 |
| Audio-only | 5 | Median IoU | 0.600000 | 0.347826 | -0.252174 |
| Audio-only | 5 | IoU >= 0.5 count | 3 | 1 | -2 |
| Audio-only | 5 | Coverage | 32.55% | 17.36% | -15.19 pp |
| Audio-only | 10 | Mean IoU | 0.465128 | 0.320124 | -0.145005 |
| Audio-only | 10 | Median IoU | 0.425725 | 0.276190 | -0.149534 |
| Audio-only | 10 | IoU >= 0.5 count | 4 | 1 | -3 |
| Audio-only | 10 | Coverage | 64.66% | 34.28% | -30.38 pp |
| Audio + Scene | 5 | Mean IoU | 0.517504 | 0.377916 | -0.139588 |
| Audio + Scene | 5 | Median IoU | 0.600000 | 0.347826 | -0.252174 |
| Audio + Scene | 5 | IoU >= 0.5 count | 3 | 1 | -2 |
| Audio + Scene | 5 | Coverage | 32.55% | 17.36% | -15.19 pp |
| Audio + Scene | 10 | Mean IoU | 0.465128 | 0.320124 | -0.145005 |
| Audio + Scene | 10 | Median IoU | 0.425725 | 0.276190 | -0.149534 |
| Audio + Scene | 10 | IoU >= 0.5 count | 4 | 1 | -3 |
| Audio + Scene | 10 | Coverage | 64.66% | 34.28% | -30.38 pp |
| Audio + Motion | 5 | Mean IoU | 0.509891 | 0.349135 | -0.160756 |
| Audio + Motion | 5 | Median IoU | 0.536862 | 0.347826 | -0.189036 |
| Audio + Motion | 5 | IoU >= 0.5 count | 3 | 0 | -3 |
| Audio + Motion | 5 | Coverage | 30.57% | 17.36% | -13.21 pp |
| Audio + Motion | 10 | Mean IoU | 0.477886 | 0.320121 | -0.157765 |
| Audio + Motion | 10 | Median IoU | 0.467391 | 0.276190 | -0.191201 |
| Audio + Motion | 10 | IoU >= 0.5 count | 5 | 1 | -4 |
| Audio + Motion | 10 | Coverage | 62.68% | 34.28% | -28.40 pp |

## Audio-only — Top 5

Candidate timestamps: 40, 69, 84, 146, 170

| Candidate | Fixed start/end | Dynamic start/end | Duration | Baseline / threshold | Left / right stop | Minimum padded | Best IoU |
|---:|---|---|---:|---|---|---|---:|
| 40 | 30.000-45.000 | 35.500-43.500 | 8.000 | 0.339283 / 0.415829 | quiet_region / quiet_region | True | 0.571429 |
| 69 | 59.000-74.000 | 64.500-72.500 | 8.000 | 0.345668 / 0.438414 | quiet_region / quiet_region | True | 0.347826 |
| 84 | 74.000-89.000 | 79.500-87.500 | 8.000 | 0.345668 / 0.509251 | quiet_region / quiet_region | True | 0.478261 |
| 146 | 136.000-151.000 | 142.000-150.000 | 8.000 | 0.349420 / 0.444614 | quiet_region / quiet_region | True | 0.222222 |
| 170 | 160.000-175.000 | 166.500-174.500 | 8.000 | 0.368403 / 0.510371 | quiet_region / quiet_region | True | 0.285714 |

| GT start/end | Type | Fixed covered seconds | Dynamic covered seconds | Dynamic coverage |
|---|---|---:|---:|---:|
| 0-18 | intro | 0.000000 | 0.000000 | 0.00% |
| 19-27 | transition | 0.000000 | 0.000000 | 0.00% |
| 27-33 | combat | 3.000000 | 0.000000 | 0.00% |
| 33-47 | combat | 12.000000 | 8.000000 | 57.14% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.00% |
| 53-76 | combat | 17.000000 | 8.000000 | 34.78% |
| 76-85 | combat | 9.000000 | 5.500000 | 61.11% |
| 85-92 | victory | 4.000000 | 2.500000 | 35.71% |
| 92-122 | combat | 0.000000 | 0.000000 | 0.00% |
| 122-158 | combat | 15.000000 | 8.000000 | 22.22% |
| 158-164 | transition | 4.000000 | 0.000000 | 0.00% |
| 164-192 | combat | 11.000000 | 8.000000 | 28.57% |
| 192-212 | combat | 0.000000 | 0.000000 | 0.00% |
| 212-231.433 | victory | 0.000000 | 0.000000 | 0.00% |

## Audio-only — Top 10

Candidate timestamps: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217

| Candidate | Fixed start/end | Dynamic start/end | Duration | Baseline / threshold | Left / right stop | Minimum padded | Best IoU |
|---:|---|---|---:|---|---|---|---:|
| 18 | 8.000-23.000 | 14.000-22.000 | 8.000 | 0.385862 / 0.432386 | quiet_region / quiet_region | True | 0.230769 |
| 40 | 30.000-45.000 | 35.500-43.500 | 8.000 | 0.339283 / 0.415829 | quiet_region / quiet_region | True | 0.571429 |
| 69 | 59.000-74.000 | 64.500-72.500 | 8.000 | 0.345668 / 0.438414 | quiet_region / quiet_region | True | 0.347826 |
| 84 | 74.000-89.000 | 79.500-87.500 | 8.000 | 0.345668 / 0.509251 | quiet_region / quiet_region | True | 0.478261 |
| 103 | 93.000-108.000 | 100.500-108.500 | 8.000 | 0.377192 / 0.419732 | quiet_region / quiet_region | True | 0.266667 |
| 122 | 112.000-127.000 | 115.500-123.500 | 8.000 | 0.396044 / 0.451833 | quiet_region / quiet_region | True | 0.206349 |
| 146 | 136.000-151.000 | 142.000-150.000 | 8.000 | 0.349420 / 0.444614 | quiet_region / quiet_region | True | 0.222222 |
| 170 | 160.000-175.000 | 166.500-174.500 | 8.000 | 0.368403 / 0.510371 | quiet_region / quiet_region | True | 0.285714 |
| 192 | 182.000-197.000 | 186.500-194.500 | 8.000 | 0.308395 / 0.357271 | quiet_region / quiet_region | True | 0.180328 |
| 217 | 207.000-222.000 | 213.500-221.500 | 8.000 | 0.234098 / 0.336613 | quiet_region / quiet_region | True | 0.411671 |

| GT start/end | Type | Fixed covered seconds | Dynamic covered seconds | Dynamic coverage |
|---|---|---:|---:|---:|
| 0-18 | intro | 10.000000 | 4.000000 | 22.22% |
| 19-27 | transition | 4.000000 | 3.000000 | 37.50% |
| 27-33 | combat | 3.000000 | 0.000000 | 0.00% |
| 33-47 | combat | 12.000000 | 8.000000 | 57.14% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.00% |
| 53-76 | combat | 17.000000 | 8.000000 | 34.78% |
| 76-85 | combat | 9.000000 | 5.500000 | 61.11% |
| 85-92 | victory | 4.000000 | 2.500000 | 35.71% |
| 92-122 | combat | 25.000000 | 14.500000 | 48.33% |
| 122-158 | combat | 20.000000 | 9.500000 | 26.39% |
| 158-164 | transition | 4.000000 | 0.000000 | 0.00% |
| 164-192 | combat | 21.000000 | 13.500000 | 48.21% |
| 192-212 | combat | 10.000000 | 2.500000 | 12.50% |
| 212-231.433 | victory | 10.000000 | 8.000000 | 41.17% |

## Audio + Scene — Top 5

Candidate timestamps: 40, 69, 84, 122, 170

| Candidate | Fixed start/end | Dynamic start/end | Duration | Baseline / threshold | Left / right stop | Minimum padded | Best IoU |
|---:|---|---|---:|---|---|---|---:|
| 40 | 30.000-45.000 | 35.500-43.500 | 8.000 | 0.339283 / 0.415829 | quiet_region / quiet_region | True | 0.571429 |
| 69 | 59.000-74.000 | 64.500-72.500 | 8.000 | 0.345668 / 0.438414 | quiet_region / quiet_region | True | 0.347826 |
| 84 | 74.000-89.000 | 79.500-87.500 | 8.000 | 0.345668 / 0.509251 | quiet_region / quiet_region | True | 0.478261 |
| 122 | 112.000-127.000 | 115.500-123.500 | 8.000 | 0.396044 / 0.451833 | quiet_region / quiet_region | True | 0.206349 |
| 170 | 160.000-175.000 | 166.500-174.500 | 8.000 | 0.368403 / 0.510371 | quiet_region / quiet_region | True | 0.285714 |

| GT start/end | Type | Fixed covered seconds | Dynamic covered seconds | Dynamic coverage |
|---|---|---:|---:|---:|
| 0-18 | intro | 0.000000 | 0.000000 | 0.00% |
| 19-27 | transition | 0.000000 | 0.000000 | 0.00% |
| 27-33 | combat | 3.000000 | 0.000000 | 0.00% |
| 33-47 | combat | 12.000000 | 8.000000 | 57.14% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.00% |
| 53-76 | combat | 17.000000 | 8.000000 | 34.78% |
| 76-85 | combat | 9.000000 | 5.500000 | 61.11% |
| 85-92 | victory | 4.000000 | 2.500000 | 35.71% |
| 92-122 | combat | 10.000000 | 6.500000 | 21.67% |
| 122-158 | combat | 5.000000 | 1.500000 | 4.17% |
| 158-164 | transition | 4.000000 | 0.000000 | 0.00% |
| 164-192 | combat | 11.000000 | 8.000000 | 28.57% |
| 192-212 | combat | 0.000000 | 0.000000 | 0.00% |
| 212-231.433 | victory | 0.000000 | 0.000000 | 0.00% |

## Audio + Scene — Top 10

Candidate timestamps: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217

| Candidate | Fixed start/end | Dynamic start/end | Duration | Baseline / threshold | Left / right stop | Minimum padded | Best IoU |
|---:|---|---|---:|---|---|---|---:|
| 18 | 8.000-23.000 | 14.000-22.000 | 8.000 | 0.385862 / 0.432386 | quiet_region / quiet_region | True | 0.230769 |
| 40 | 30.000-45.000 | 35.500-43.500 | 8.000 | 0.339283 / 0.415829 | quiet_region / quiet_region | True | 0.571429 |
| 69 | 59.000-74.000 | 64.500-72.500 | 8.000 | 0.345668 / 0.438414 | quiet_region / quiet_region | True | 0.347826 |
| 84 | 74.000-89.000 | 79.500-87.500 | 8.000 | 0.345668 / 0.509251 | quiet_region / quiet_region | True | 0.478261 |
| 103 | 93.000-108.000 | 100.500-108.500 | 8.000 | 0.377192 / 0.419732 | quiet_region / quiet_region | True | 0.266667 |
| 122 | 112.000-127.000 | 115.500-123.500 | 8.000 | 0.396044 / 0.451833 | quiet_region / quiet_region | True | 0.206349 |
| 146 | 136.000-151.000 | 142.000-150.000 | 8.000 | 0.349420 / 0.444614 | quiet_region / quiet_region | True | 0.222222 |
| 170 | 160.000-175.000 | 166.500-174.500 | 8.000 | 0.368403 / 0.510371 | quiet_region / quiet_region | True | 0.285714 |
| 192 | 182.000-197.000 | 186.500-194.500 | 8.000 | 0.308395 / 0.357271 | quiet_region / quiet_region | True | 0.180328 |
| 217 | 207.000-222.000 | 213.500-221.500 | 8.000 | 0.234098 / 0.336613 | quiet_region / quiet_region | True | 0.411671 |

| GT start/end | Type | Fixed covered seconds | Dynamic covered seconds | Dynamic coverage |
|---|---|---:|---:|---:|
| 0-18 | intro | 10.000000 | 4.000000 | 22.22% |
| 19-27 | transition | 4.000000 | 3.000000 | 37.50% |
| 27-33 | combat | 3.000000 | 0.000000 | 0.00% |
| 33-47 | combat | 12.000000 | 8.000000 | 57.14% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.00% |
| 53-76 | combat | 17.000000 | 8.000000 | 34.78% |
| 76-85 | combat | 9.000000 | 5.500000 | 61.11% |
| 85-92 | victory | 4.000000 | 2.500000 | 35.71% |
| 92-122 | combat | 25.000000 | 14.500000 | 48.33% |
| 122-158 | combat | 20.000000 | 9.500000 | 26.39% |
| 158-164 | transition | 4.000000 | 0.000000 | 0.00% |
| 164-192 | combat | 21.000000 | 13.500000 | 48.21% |
| 192-212 | combat | 10.000000 | 2.500000 | 12.50% |
| 212-231.433 | victory | 10.000000 | 8.000000 | 41.17% |

## Audio + Motion — Top 5

Candidate timestamps: 69, 84, 146, 170, 231

| Candidate | Fixed start/end | Dynamic start/end | Duration | Baseline / threshold | Left / right stop | Minimum padded | Best IoU |
|---:|---|---|---:|---|---|---|---:|
| 69 | 59.000-74.000 | 64.500-72.500 | 8.000 | 0.345668 / 0.438414 | quiet_region / quiet_region | True | 0.347826 |
| 84 | 74.000-89.000 | 79.500-87.500 | 8.000 | 0.345668 / 0.509251 | quiet_region / quiet_region | True | 0.478261 |
| 146 | 136.000-151.000 | 142.000-150.000 | 8.000 | 0.349420 / 0.444614 | quiet_region / quiet_region | True | 0.222222 |
| 170 | 160.000-175.000 | 166.500-174.500 | 8.000 | 0.368403 / 0.510371 | quiet_region / quiet_region | True | 0.285714 |
| 231 | 221.000-231.433 | 223.433-231.433 | 8.000 | 0.301026 / 0.382163 | quiet_region / video_boundary | True | 0.411650 |

| GT start/end | Type | Fixed covered seconds | Dynamic covered seconds | Dynamic coverage |
|---|---|---:|---:|---:|
| 0-18 | intro | 0.000000 | 0.000000 | 0.00% |
| 19-27 | transition | 0.000000 | 0.000000 | 0.00% |
| 27-33 | combat | 0.000000 | 0.000000 | 0.00% |
| 33-47 | combat | 0.000000 | 0.000000 | 0.00% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.00% |
| 53-76 | combat | 17.000000 | 8.000000 | 34.78% |
| 76-85 | combat | 9.000000 | 5.500000 | 61.11% |
| 85-92 | victory | 4.000000 | 2.500000 | 35.71% |
| 92-122 | combat | 0.000000 | 0.000000 | 0.00% |
| 122-158 | combat | 15.000000 | 8.000000 | 22.22% |
| 158-164 | transition | 4.000000 | 0.000000 | 0.00% |
| 164-192 | combat | 11.000000 | 8.000000 | 28.57% |
| 192-212 | combat | 0.000000 | 0.000000 | 0.00% |
| 212-231.433 | victory | 10.433000 | 7.999712 | 41.17% |

## Audio + Motion — Top 10

Candidate timestamps: 18, 40, 69, 84, 103, 122, 146, 170, 192, 231

| Candidate | Fixed start/end | Dynamic start/end | Duration | Baseline / threshold | Left / right stop | Minimum padded | Best IoU |
|---:|---|---|---:|---|---|---|---:|
| 18 | 8.000-23.000 | 14.000-22.000 | 8.000 | 0.385862 / 0.432386 | quiet_region / quiet_region | True | 0.230769 |
| 40 | 30.000-45.000 | 35.500-43.500 | 8.000 | 0.339283 / 0.415829 | quiet_region / quiet_region | True | 0.571429 |
| 69 | 59.000-74.000 | 64.500-72.500 | 8.000 | 0.345668 / 0.438414 | quiet_region / quiet_region | True | 0.347826 |
| 84 | 74.000-89.000 | 79.500-87.500 | 8.000 | 0.345668 / 0.509251 | quiet_region / quiet_region | True | 0.478261 |
| 103 | 93.000-108.000 | 100.500-108.500 | 8.000 | 0.377192 / 0.419732 | quiet_region / quiet_region | True | 0.266667 |
| 122 | 112.000-127.000 | 115.500-123.500 | 8.000 | 0.396044 / 0.451833 | quiet_region / quiet_region | True | 0.206349 |
| 146 | 136.000-151.000 | 142.000-150.000 | 8.000 | 0.349420 / 0.444614 | quiet_region / quiet_region | True | 0.222222 |
| 170 | 160.000-175.000 | 166.500-174.500 | 8.000 | 0.368403 / 0.510371 | quiet_region / quiet_region | True | 0.285714 |
| 192 | 182.000-197.000 | 186.500-194.500 | 8.000 | 0.308395 / 0.357271 | quiet_region / quiet_region | True | 0.180328 |
| 231 | 221.000-231.433 | 223.433-231.433 | 8.000 | 0.301026 / 0.382163 | quiet_region / video_boundary | True | 0.411650 |

| GT start/end | Type | Fixed covered seconds | Dynamic covered seconds | Dynamic coverage |
|---|---|---:|---:|---:|
| 0-18 | intro | 10.000000 | 4.000000 | 22.22% |
| 19-27 | transition | 4.000000 | 3.000000 | 37.50% |
| 27-33 | combat | 3.000000 | 0.000000 | 0.00% |
| 33-47 | combat | 12.000000 | 8.000000 | 57.14% |
| 47-53 | combat | 0.000000 | 0.000000 | 0.00% |
| 53-76 | combat | 17.000000 | 8.000000 | 34.78% |
| 76-85 | combat | 9.000000 | 5.500000 | 61.11% |
| 85-92 | victory | 4.000000 | 2.500000 | 35.71% |
| 92-122 | combat | 25.000000 | 14.500000 | 48.33% |
| 122-158 | combat | 20.000000 | 9.500000 | 26.39% |
| 158-164 | transition | 4.000000 | 0.000000 | 0.00% |
| 164-192 | combat | 21.000000 | 13.500000 | 48.21% |
| 192-212 | combat | 5.000000 | 2.500000 | 12.50% |
| 212-231.433 | victory | 10.433000 | 7.999712 | 41.17% |

## Interpretation limits

These measurements describe boundary changes, not a detector ranking or overall quality score. Increased coverage can follow longer windows without better boundaries. IoU depends on annotation length. The audio score can reflect music or commentary; a locally constant signal is quiet under this relative rule. The first five audio seconds are unavailable; minimum padding can include quiet or missing regions. This experiment cannot establish generalization or guarantee complete gameplay sequences.

Reproduce with `python evaluate_dynamic_windows.py`. The runner saves detailed numerical boundary traces to ignored `output/dynamic_window_v1.json` and overwrites this experimental report, never the frozen fixed report.

Frozen baseline SHA-256: `93f141736c8a8a9da2575a7f5efcc4b61ceaff72ec48e8f2710d36050c16bab4`

Source SHA-256:

- `main.py`: `379abfef0b75860feb2f642aa02a53f650a90dbf6ce18d082cdd63a0aa583f4e`
- `motion.py`: `932da2a0839cae1d440e6fa4b895a242c619cbc318686ee05943c5d0650e5d9d`
- `evaluation.py`: `2e0a83a392fb9ce8c64b00447a4981fc9e9da781977bd469de13e976cafe73fc`
- `evaluation_v2.py`: `35acac250ad02ce12b8159554cc42b95468b776b96e4d8f94cdf35a3f372da16`
- `windows.py`: `43f080b8beae53ef54c46e816b68bea4267d1497f822b3a1b33a178c81d9230b`
- `dynamic_windows.py`: `abd38b0cebc498893e6a9c78ed2c88133ca2cfdd8a7ff89f8a2e50e5b200c73b`
- `evaluate_dynamic_windows.py`: `433841c146d5721fab38628182cd4e98c4857612fbf157474c2b4512d12fe814`
- `ground_truth_v2.json`: `2fbf544b7994454bcc43dab93b1bf1295a45cec7055de6405762258f6694a8a1`
- `videos/my_recording.mp4`: `6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09`
