# Fixed-window Ground Truth V2 baseline

## Experiment setup

Real source: `videos/my_recording.mp4`, duration **231.433288 seconds**.
One already-edited Minecraft BedWars video; 14 human-labeled semantic V2 intervals.
Candidates come directly from the existing main.py run. Audio scoring, scene/motion signals, 70/30 weights, and +/-5s visual association remain unchanged.
For each detector, the existing score ranking and greedy 15-second timestamp suppression select Top 5 and Top 10, then return chronological candidates.
Fixed **[-10,+5] second** windows: start=max(0, second-10), end=min(video_duration, second+5). No dynamic cuts or window selection changes.

IoU **0.5 is an experimental reporting threshold, not a validated cutoff**. Each prediction independently uses its highest positive GT IoU; ties use GT order. GT is not consumed. Mean/median include zero IoUs for unmatched predictions.
Coverage counts the intersection of prediction union and annotated union, divided by annotated-union duration. Overlaps are not double-counted; gaps are excluded.

## Summary

| Detector | K | Mean best IoU | Median best IoU | IoU >= 0.5 | Covered / annotated seconds | Coverage |
|---|---:|---:|---:|---:|---:|---:|
| Audio-only | 5 | 0.543695 | 0.600000 | 3/5 | 75.000000 / 230.433000 | 32.55% |
| Audio-only | 10 | 0.465128 | 0.425725 | 4/10 | 149.000000 / 230.433000 | 64.66% |
| Audio + Scene | 5 | 0.517504 | 0.600000 | 3/5 | 75.000000 / 230.433000 | 32.55% |
| Audio + Scene | 10 | 0.465128 | 0.425725 | 4/10 | 149.000000 / 230.433000 | 64.66% |
| Audio + Motion | 5 | 0.509891 | 0.536862 | 3/5 | 70.433000 / 230.433000 | 30.57% |
| Audio + Motion | 10 | 0.477886 | 0.467391 | 5/10 | 144.433000 / 230.433000 | 62.68% |

## Audio-only — Top 5

Selected timestamps (seconds): 40, 69, 84, 146, 170

| Candidate (s) | Window start (s) | Window end (s) | Best GT interval (s) | Best IoU |
|---:|---:|---:|---|---:|
| 40 | 30.000000 | 45.000000 | 33-47 | 0.705882 |
| 69 | 59.000000 | 74.000000 | 53-76 | 0.652174 |
| 84 | 74.000000 | 89.000000 | 76-85 | 0.600000 |
| 146 | 136.000000 | 151.000000 | 122-158 | 0.416667 |
| 170 | 160.000000 | 175.000000 | 164-192 | 0.343750 |

| GT interval (s) | Type | Description | Duration (s) | Covered (s) | Coverage |
|---|---|---|---:|---:|---:|
| 0-18 | intro | video intro | 18.000000 | 0.000000 | 0.00% |
| 19-27 | transition | Game 1 transition and initial reaction to pack | 8.000000 | 0.000000 | 0.00% |
| 27-33 | combat | Bridging and get fireballed off the map | 6.000000 | 3.000000 | 50.00% |
| 33-47 | combat | Kill player, break bed, then get final kill | 14.000000 | 12.000000 | 85.71% |
| 47-53 | combat | Break another bed, get fireballed to death | 6.000000 | 0.000000 | 0.00% |
| 53-76 | combat | Killed by Aqua, skybridge fight, almost kill him but lose due to armor | 23.000000 | 17.000000 | 73.91% |
| 76-85 | combat | Aqua breaks my bed, then I combo him and kill him | 9.000000 | 9.000000 | 100.00% |
| 85-92 | victory | Break bed, win Game 1, then transition to Game 2 | 7.000000 | 4.000000 | 57.14% |
| 92-122 | combat | Bridge, fireball Yellow to death, kill him twice more, break bed, then combo for final kill | 30.000000 | 0.000000 | 0.00% |
| 122-158 | combat | Aqua fireballs and kills me, I search for him while invisible, he kills me again, then fights me at base, breaks my bed, and gets the final kill | 36.000000 | 15.000000 | 41.67% |
| 158-164 | transition | Game 3 transition | 6.000000 | 4.000000 | 66.67% |
| 164-192 | combat | Combo Red, he kills me, bridge fight, he TNT jumps behind me, breaks my bed, then I kill him | 28.000000 | 11.000000 | 39.29% |
| 192-212 | combat | Collect emeralds at mid, kill Green, then Yellow attacks and I kill him too | 20.000000 | 0.000000 | 0.00% |
| 212-231.433 | victory | Kill player at his bed, break bed, get final kill, then victory | 19.433000 | 0.000000 | 0.00% |

## Audio-only — Top 10

Selected timestamps (seconds): 18, 40, 69, 84, 103, 122, 146, 170, 192, 217

| Candidate (s) | Window start (s) | Window end (s) | Best GT interval (s) | Best IoU |
|---:|---:|---:|---|---:|
| 18 | 8.000000 | 23.000000 | 0-18 | 0.434783 |
| 40 | 30.000000 | 45.000000 | 33-47 | 0.705882 |
| 69 | 59.000000 | 74.000000 | 53-76 | 0.652174 |
| 84 | 74.000000 | 89.000000 | 76-85 | 0.600000 |
| 103 | 93.000000 | 108.000000 | 92-122 | 0.500000 |
| 122 | 112.000000 | 127.000000 | 92-122 | 0.285714 |
| 146 | 136.000000 | 151.000000 | 122-158 | 0.416667 |
| 170 | 160.000000 | 175.000000 | 164-192 | 0.343750 |
| 192 | 182.000000 | 197.000000 | 164-192 | 0.303030 |
| 217 | 207.000000 | 222.000000 | 212-231.433 | 0.409283 |

| GT interval (s) | Type | Description | Duration (s) | Covered (s) | Coverage |
|---|---|---|---:|---:|---:|
| 0-18 | intro | video intro | 18.000000 | 10.000000 | 55.56% |
| 19-27 | transition | Game 1 transition and initial reaction to pack | 8.000000 | 4.000000 | 50.00% |
| 27-33 | combat | Bridging and get fireballed off the map | 6.000000 | 3.000000 | 50.00% |
| 33-47 | combat | Kill player, break bed, then get final kill | 14.000000 | 12.000000 | 85.71% |
| 47-53 | combat | Break another bed, get fireballed to death | 6.000000 | 0.000000 | 0.00% |
| 53-76 | combat | Killed by Aqua, skybridge fight, almost kill him but lose due to armor | 23.000000 | 17.000000 | 73.91% |
| 76-85 | combat | Aqua breaks my bed, then I combo him and kill him | 9.000000 | 9.000000 | 100.00% |
| 85-92 | victory | Break bed, win Game 1, then transition to Game 2 | 7.000000 | 4.000000 | 57.14% |
| 92-122 | combat | Bridge, fireball Yellow to death, kill him twice more, break bed, then combo for final kill | 30.000000 | 25.000000 | 83.33% |
| 122-158 | combat | Aqua fireballs and kills me, I search for him while invisible, he kills me again, then fights me at base, breaks my bed, and gets the final kill | 36.000000 | 20.000000 | 55.56% |
| 158-164 | transition | Game 3 transition | 6.000000 | 4.000000 | 66.67% |
| 164-192 | combat | Combo Red, he kills me, bridge fight, he TNT jumps behind me, breaks my bed, then I kill him | 28.000000 | 21.000000 | 75.00% |
| 192-212 | combat | Collect emeralds at mid, kill Green, then Yellow attacks and I kill him too | 20.000000 | 10.000000 | 50.00% |
| 212-231.433 | victory | Kill player at his bed, break bed, get final kill, then victory | 19.433000 | 10.000000 | 51.46% |

## Audio + Scene — Top 5

Selected timestamps (seconds): 40, 69, 84, 122, 170

| Candidate (s) | Window start (s) | Window end (s) | Best GT interval (s) | Best IoU |
|---:|---:|---:|---|---:|
| 40 | 30.000000 | 45.000000 | 33-47 | 0.705882 |
| 69 | 59.000000 | 74.000000 | 53-76 | 0.652174 |
| 84 | 74.000000 | 89.000000 | 76-85 | 0.600000 |
| 122 | 112.000000 | 127.000000 | 92-122 | 0.285714 |
| 170 | 160.000000 | 175.000000 | 164-192 | 0.343750 |

| GT interval (s) | Type | Description | Duration (s) | Covered (s) | Coverage |
|---|---|---|---:|---:|---:|
| 0-18 | intro | video intro | 18.000000 | 0.000000 | 0.00% |
| 19-27 | transition | Game 1 transition and initial reaction to pack | 8.000000 | 0.000000 | 0.00% |
| 27-33 | combat | Bridging and get fireballed off the map | 6.000000 | 3.000000 | 50.00% |
| 33-47 | combat | Kill player, break bed, then get final kill | 14.000000 | 12.000000 | 85.71% |
| 47-53 | combat | Break another bed, get fireballed to death | 6.000000 | 0.000000 | 0.00% |
| 53-76 | combat | Killed by Aqua, skybridge fight, almost kill him but lose due to armor | 23.000000 | 17.000000 | 73.91% |
| 76-85 | combat | Aqua breaks my bed, then I combo him and kill him | 9.000000 | 9.000000 | 100.00% |
| 85-92 | victory | Break bed, win Game 1, then transition to Game 2 | 7.000000 | 4.000000 | 57.14% |
| 92-122 | combat | Bridge, fireball Yellow to death, kill him twice more, break bed, then combo for final kill | 30.000000 | 10.000000 | 33.33% |
| 122-158 | combat | Aqua fireballs and kills me, I search for him while invisible, he kills me again, then fights me at base, breaks my bed, and gets the final kill | 36.000000 | 5.000000 | 13.89% |
| 158-164 | transition | Game 3 transition | 6.000000 | 4.000000 | 66.67% |
| 164-192 | combat | Combo Red, he kills me, bridge fight, he TNT jumps behind me, breaks my bed, then I kill him | 28.000000 | 11.000000 | 39.29% |
| 192-212 | combat | Collect emeralds at mid, kill Green, then Yellow attacks and I kill him too | 20.000000 | 0.000000 | 0.00% |
| 212-231.433 | victory | Kill player at his bed, break bed, get final kill, then victory | 19.433000 | 0.000000 | 0.00% |

## Audio + Scene — Top 10

Selected timestamps (seconds): 18, 40, 69, 84, 103, 122, 146, 170, 192, 217

| Candidate (s) | Window start (s) | Window end (s) | Best GT interval (s) | Best IoU |
|---:|---:|---:|---|---:|
| 18 | 8.000000 | 23.000000 | 0-18 | 0.434783 |
| 40 | 30.000000 | 45.000000 | 33-47 | 0.705882 |
| 69 | 59.000000 | 74.000000 | 53-76 | 0.652174 |
| 84 | 74.000000 | 89.000000 | 76-85 | 0.600000 |
| 103 | 93.000000 | 108.000000 | 92-122 | 0.500000 |
| 122 | 112.000000 | 127.000000 | 92-122 | 0.285714 |
| 146 | 136.000000 | 151.000000 | 122-158 | 0.416667 |
| 170 | 160.000000 | 175.000000 | 164-192 | 0.343750 |
| 192 | 182.000000 | 197.000000 | 164-192 | 0.303030 |
| 217 | 207.000000 | 222.000000 | 212-231.433 | 0.409283 |

| GT interval (s) | Type | Description | Duration (s) | Covered (s) | Coverage |
|---|---|---|---:|---:|---:|
| 0-18 | intro | video intro | 18.000000 | 10.000000 | 55.56% |
| 19-27 | transition | Game 1 transition and initial reaction to pack | 8.000000 | 4.000000 | 50.00% |
| 27-33 | combat | Bridging and get fireballed off the map | 6.000000 | 3.000000 | 50.00% |
| 33-47 | combat | Kill player, break bed, then get final kill | 14.000000 | 12.000000 | 85.71% |
| 47-53 | combat | Break another bed, get fireballed to death | 6.000000 | 0.000000 | 0.00% |
| 53-76 | combat | Killed by Aqua, skybridge fight, almost kill him but lose due to armor | 23.000000 | 17.000000 | 73.91% |
| 76-85 | combat | Aqua breaks my bed, then I combo him and kill him | 9.000000 | 9.000000 | 100.00% |
| 85-92 | victory | Break bed, win Game 1, then transition to Game 2 | 7.000000 | 4.000000 | 57.14% |
| 92-122 | combat | Bridge, fireball Yellow to death, kill him twice more, break bed, then combo for final kill | 30.000000 | 25.000000 | 83.33% |
| 122-158 | combat | Aqua fireballs and kills me, I search for him while invisible, he kills me again, then fights me at base, breaks my bed, and gets the final kill | 36.000000 | 20.000000 | 55.56% |
| 158-164 | transition | Game 3 transition | 6.000000 | 4.000000 | 66.67% |
| 164-192 | combat | Combo Red, he kills me, bridge fight, he TNT jumps behind me, breaks my bed, then I kill him | 28.000000 | 21.000000 | 75.00% |
| 192-212 | combat | Collect emeralds at mid, kill Green, then Yellow attacks and I kill him too | 20.000000 | 10.000000 | 50.00% |
| 212-231.433 | victory | Kill player at his bed, break bed, get final kill, then victory | 19.433000 | 10.000000 | 51.46% |

## Audio + Motion — Top 5

Selected timestamps (seconds): 69, 84, 146, 170, 231

| Candidate (s) | Window start (s) | Window end (s) | Best GT interval (s) | Best IoU |
|---:|---:|---:|---|---:|
| 69 | 59.000000 | 74.000000 | 53-76 | 0.652174 |
| 84 | 74.000000 | 89.000000 | 76-85 | 0.600000 |
| 146 | 136.000000 | 151.000000 | 122-158 | 0.416667 |
| 170 | 160.000000 | 175.000000 | 164-192 | 0.343750 |
| 231 | 221.000000 | 231.433288 | 212-231.433 | 0.536862 |

| GT interval (s) | Type | Description | Duration (s) | Covered (s) | Coverage |
|---|---|---|---:|---:|---:|
| 0-18 | intro | video intro | 18.000000 | 0.000000 | 0.00% |
| 19-27 | transition | Game 1 transition and initial reaction to pack | 8.000000 | 0.000000 | 0.00% |
| 27-33 | combat | Bridging and get fireballed off the map | 6.000000 | 0.000000 | 0.00% |
| 33-47 | combat | Kill player, break bed, then get final kill | 14.000000 | 0.000000 | 0.00% |
| 47-53 | combat | Break another bed, get fireballed to death | 6.000000 | 0.000000 | 0.00% |
| 53-76 | combat | Killed by Aqua, skybridge fight, almost kill him but lose due to armor | 23.000000 | 17.000000 | 73.91% |
| 76-85 | combat | Aqua breaks my bed, then I combo him and kill him | 9.000000 | 9.000000 | 100.00% |
| 85-92 | victory | Break bed, win Game 1, then transition to Game 2 | 7.000000 | 4.000000 | 57.14% |
| 92-122 | combat | Bridge, fireball Yellow to death, kill him twice more, break bed, then combo for final kill | 30.000000 | 0.000000 | 0.00% |
| 122-158 | combat | Aqua fireballs and kills me, I search for him while invisible, he kills me again, then fights me at base, breaks my bed, and gets the final kill | 36.000000 | 15.000000 | 41.67% |
| 158-164 | transition | Game 3 transition | 6.000000 | 4.000000 | 66.67% |
| 164-192 | combat | Combo Red, he kills me, bridge fight, he TNT jumps behind me, breaks my bed, then I kill him | 28.000000 | 11.000000 | 39.29% |
| 192-212 | combat | Collect emeralds at mid, kill Green, then Yellow attacks and I kill him too | 20.000000 | 0.000000 | 0.00% |
| 212-231.433 | victory | Kill player at his bed, break bed, get final kill, then victory | 19.433000 | 10.433000 | 53.69% |

## Audio + Motion — Top 10

Selected timestamps (seconds): 18, 40, 69, 84, 103, 122, 146, 170, 192, 231

| Candidate (s) | Window start (s) | Window end (s) | Best GT interval (s) | Best IoU |
|---:|---:|---:|---|---:|
| 18 | 8.000000 | 23.000000 | 0-18 | 0.434783 |
| 40 | 30.000000 | 45.000000 | 33-47 | 0.705882 |
| 69 | 59.000000 | 74.000000 | 53-76 | 0.652174 |
| 84 | 74.000000 | 89.000000 | 76-85 | 0.600000 |
| 103 | 93.000000 | 108.000000 | 92-122 | 0.500000 |
| 122 | 112.000000 | 127.000000 | 92-122 | 0.285714 |
| 146 | 136.000000 | 151.000000 | 122-158 | 0.416667 |
| 170 | 160.000000 | 175.000000 | 164-192 | 0.343750 |
| 192 | 182.000000 | 197.000000 | 164-192 | 0.303030 |
| 231 | 221.000000 | 231.433288 | 212-231.433 | 0.536862 |

| GT interval (s) | Type | Description | Duration (s) | Covered (s) | Coverage |
|---|---|---|---:|---:|---:|
| 0-18 | intro | video intro | 18.000000 | 10.000000 | 55.56% |
| 19-27 | transition | Game 1 transition and initial reaction to pack | 8.000000 | 4.000000 | 50.00% |
| 27-33 | combat | Bridging and get fireballed off the map | 6.000000 | 3.000000 | 50.00% |
| 33-47 | combat | Kill player, break bed, then get final kill | 14.000000 | 12.000000 | 85.71% |
| 47-53 | combat | Break another bed, get fireballed to death | 6.000000 | 0.000000 | 0.00% |
| 53-76 | combat | Killed by Aqua, skybridge fight, almost kill him but lose due to armor | 23.000000 | 17.000000 | 73.91% |
| 76-85 | combat | Aqua breaks my bed, then I combo him and kill him | 9.000000 | 9.000000 | 100.00% |
| 85-92 | victory | Break bed, win Game 1, then transition to Game 2 | 7.000000 | 4.000000 | 57.14% |
| 92-122 | combat | Bridge, fireball Yellow to death, kill him twice more, break bed, then combo for final kill | 30.000000 | 25.000000 | 83.33% |
| 122-158 | combat | Aqua fireballs and kills me, I search for him while invisible, he kills me again, then fights me at base, breaks my bed, and gets the final kill | 36.000000 | 20.000000 | 55.56% |
| 158-164 | transition | Game 3 transition | 6.000000 | 4.000000 | 66.67% |
| 164-192 | combat | Combo Red, he kills me, bridge fight, he TNT jumps behind me, breaks my bed, then I kill him | 28.000000 | 21.000000 | 75.00% |
| 192-212 | combat | Collect emeralds at mid, kill Green, then Yellow attacks and I kill him too | 20.000000 | 5.000000 | 25.00% |
| 212-231.433 | victory | Kill player at his bed, break bed, get final kill, then victory | 19.433000 | 10.433000 | 53.69% |

## Reproduction and limitations

Run `python evaluate_fixed_windows.py` from this checkout with FFmpeg/ffprobe and the original media available. It reruns main.py, regenerates normal clips, and replaces this report. Preserve this baseline in version control before later experiments.

This is a descriptive baseline on one edited video, not evidence of generalization. Long or short annotations affect IoU; temporal coverage measures retained annotated time, not boundary accuracy. More windows can cover more time. These are separate measurements, not an overall quality score or a detector ranking. Retention is not used. No parameters were tuned after observing results.

Source SHA-256 hashes (identify the exact assets/code used):

- `videos/my_recording.mp4`: `6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09`
- `ground_truth_v2.json`: `2fbf544b7994454bcc43dab93b1bf1295a45cec7055de6405762258f6694a8a1`
- `main.py`: `379abfef0b75860feb2f642aa02a53f650a90dbf6ce18d082cdd63a0aa583f4e`
- `motion.py`: `932da2a0839cae1d440e6fa4b895a242c619cbc318686ee05943c5d0650e5d9d`
- `evaluation.py`: `2e0a83a392fb9ce8c64b00447a4981fc9e9da781977bd469de13e976cafe73fc`
- `windows.py`: `43f080b8beae53ef54c46e816b68bea4267d1497f822b3a1b33a178c81d9230b`
- `evaluation_v2.py`: `35acac250ad02ce12b8159554cc42b95468b776b96e4d8f94cdf35a3f372da16`
- `evaluate_fixed_windows.py`: `8d112ea98c70dffc47078f90ce6de70e8e6dd11642d0d7ca53f4149697b4c2b0`
