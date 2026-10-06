# Five-second Temporal CLIP V1

Reused the existing 232-sample CLIP timeline; no inference or model download.
Model: openai/clip-vit-base-patch32; revision 3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268. Source artifact SHA-256: 7e9863f9b50b07c7d8a72c104b2c401c49722e77dcf01947e3b0869eced111ef.

## Frozen protocol

For each 1 FPS timestamp, average every label's zero_shot_score over t-2 through t+2 (five samples, fewer at edges). Use the unweighted arithmetic mean, then argmax in frozen prompt order for ties. Do not average labels or apply another softmax. Missing, duplicate, or nonuniform timestamps are rejected. Seven prompts, model, and sample frequency are unchanged.
Each sample represents [t,min(t+1,duration)); merge consecutive identical labels and exclude neutral. No thresholds or minimum duration. Event confidence holds mean winning relative evidence, not calibrated probability. Metadata preserves aggregated vectors and source neighborhoods.
Stability was computed and saved before GT loading. No parameters changed after comparison.

## Stability (before GT)

Counts/durations exclude neutral; transitions and adjacent-label retention include neutral. N/A means no events or no adjacent sample pairs.

| Metric | Raw | Temporal | Delta (temporal-raw) |
|---|---:|---:|---:|
| event_count | 143.000000 | 60.000000 | -83.000000 |
| label_transitions | 143.000000 | 59.000000 | -84.000000 |
| mean_event_duration | 1.611422 | 3.857221 | +2.245800 |
| median_event_duration | 1.000000 | 2.500000 | +1.500000 |
| longest_event_duration | 5.000000 | 18.000000 | +13.000000 |
| adjacent_same_label_fraction | 0.380952 | 0.744589 | +0.363636 |

## Event counts and same-type coverage

| Type | Raw events | Temporal events | GT intervals | GT seconds | Raw covered s | Temporal covered s | Delta s |
|---|---:|---:|---:|---:|---:|---:|---:|
| combat | 16 | 5 | 9 | 172.000000 | 15.000000 | 10.000000 | -5.000000 |
| kill | 37 | 17 | 0 | N/A | N/A | N/A | N/A |
| death | 27 | 16 | 0 | N/A | N/A | N/A | N/A |
| objective | 24 | 5 | 0 | N/A | N/A | N/A | N/A |
| transition | 4 | 1 | 2 | 14.000000 | 2.000000 | 0.000000 | -2.000000 |
| victory | 35 | 16 | 2 | 26.433000 | 5.433000 | 6.433000 | +1.000000 |
| intro | 0 | 0 | 1 | 18.000000 | 0.000000 | 0.000000 | +0.000000 |

## Temporal overlap matrix

Seconds shown as raw / temporal. Broad GT sequences are not frame-level class labels. Intro has no prompt; kills/deaths/objectives can occur inside combat. Gaps stay outside coverage.

| GT type | combat | kill | death | objective | transition | victory |
|---|---:|---:|---:|---:|---:|---:|
| intro | 0.000000 / 0.000000 | 0.000000 / 0.000000 | 8.000000 / 12.000000 | 4.000000 / 2.000000 | 4.000000 / 4.000000 | 2.000000 / 0.000000 |
| transition | 0.000000 / 0.000000 | 1.000000 / 0.000000 | 0.000000 / 1.000000 | 1.000000 / 0.000000 | 2.000000 / 0.000000 | 9.000000 / 13.000000 |
| combat | 15.000000 / 10.000000 | 54.000000 / 64.000000 | 35.000000 / 41.000000 | 25.000000 / 7.000000 | 1.000000 / 0.000000 | 42.000000 / 50.000000 |
| victory | 5.000000 / 4.000000 | 10.000000 / 14.000000 | 4.000000 / 2.000000 | 2.000000 / 0.000000 | 0.000000 / 0.000000 | 5.433000 / 6.433000 |

## Fragmentation and semantic evidence

Non-neutral event count changed from 143 to 60; label transitions changed from 143 to 59.
Fewer runs/transitions indicate reduced fragmentation, not verified semantic correctness. The coverage deltas above describe which matching-label evidence was retained, gained, or lost; they cannot prove preservation of actual kills or objectives without event-level annotations.
- GT intro / predicted death: 8.000000s -> 12.000000s (+4.000000s).
- GT intro / predicted objective: 4.000000s -> 2.000000s (-2.000000s).
- GT intro / predicted transition: 4.000000s -> 4.000000s (+0.000000s).
- GT intro / predicted victory: 2.000000s -> 0.000000s (-2.000000s).
- GT transition / predicted kill: 1.000000s -> 0.000000s (-1.000000s).
- GT transition / predicted death: 0.000000s -> 1.000000s (+1.000000s).
- GT transition / predicted objective: 1.000000s -> 0.000000s (-1.000000s).
- GT transition / predicted victory: 9.000000s -> 13.000000s (+4.000000s).
- GT combat / predicted kill: 54.000000s -> 64.000000s (+10.000000s).
- GT combat / predicted death: 35.000000s -> 41.000000s (+6.000000s).
- GT combat / predicted objective: 25.000000s -> 7.000000s (-18.000000s).
- GT combat / predicted transition: 1.000000s -> 0.000000s (-1.000000s).
- GT combat / predicted victory: 42.000000s -> 50.000000s (+8.000000s).
- GT victory / predicted combat: 5.000000s -> 4.000000s (-1.000000s).
- GT victory / predicted kill: 10.000000s -> 14.000000s (+4.000000s).
- GT victory / predicted death: 4.000000s -> 2.000000s (-2.000000s).
- GT victory / predicted objective: 2.000000s -> 0.000000s (-2.000000s).

## Frozen candidate diagnostics

Same frozen point candidates, inclusive 5s radius to event extent. Max values are relative evidence, not factual confidence. No ranking changes.

- Audio-only — Top 5: 40, 69, 84, 146, 170
- Audio-only — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217
- Audio + Scene — Top 5: 40, 69, 84, 122, 170
- Audio + Scene — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217
- Audio + Motion — Top 5: 69, 84, 146, 170, 231
- Audio + Motion — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 231

| Candidate | Raw overlap | Temporal overlap | Raw nearby | Temporal nearby |
|---:|---|---|---|---|
| 18.0 | death [17,19) | death [6,20) | death [12,16), objective [16,17), objective [20,21), victory [21,24) | victory [20,32) |
| 40.0 | kill [39,41) | victory [40,41) | kill [34,38), victory [38,39), victory [41,43), objective [43,44), kill [44,45), victory [45,47) | kill [34,40), kill [41,43), victory [43,49) |
| 69.0 | victory [68,70) | victory [61,75) | victory [63,65), death [65,66), combat [66,67), objective [67,68), objective [70,71), victory [71,74), kill [74,76) | none |
| 84.0 | kill [84,85) | combat [81,85) | death [77,80), victory [80,81), combat [81,83), objective [83,84), combat [85,86), kill [86,87), victory [87,88), kill [88,89), victory [89,91) | death [75,81), kill [85,87), victory [87,93) |
| 103.0 | objective [101,104) | objective [102,104) | death [97,99), combat [99,100), victory [100,101), death [104,105), kill [105,106), death [106,107), victory [107,108), kill [108,112) | kill [96,98), combat [98,102), death [104,107), kill [107,113) |
| 122.0 | objective [122,123) | combat [122,123) | kill [116,121), death [121,122), combat [123,125), objective [125,126), kill [126,127), death [127,129) | kill [116,122), objective [123,125), death [125,127), victory [127,133) |
| 146.0 | kill [146,147) | victory [146,147) | combat [140,141), death [141,142), kill [142,143), death [143,144), objective [144,145), death [145,146), victory [147,148), death [148,149), objective [149,150), victory [150,151), death [151,152) | victory [139,141), death [141,146), death [147,148), victory [148,150), death [150,151), victory [151,153) |
| 170.0 | death [170,173) | death [170,175) | victory [161,166), combat [166,167), kill [167,169), combat [169,170), kill [173,175), death [175,176) | victory [157,166), kill [166,170), kill [175,177) |
| 192.0 | death [192,193) | kill [192,193) | objective [186,188), kill [188,189), death [189,191), combat [191,192), objective [193,194), kill [194,195), victory [195,196), kill [196,199) | kill [178,190), death [190,192), combat [193,194), kill [194,212) |
| 217.0 | combat [216,219) | combat [216,220) | kill [211,212), victory [212,213), kill [213,214), death [214,215), kill [215,216), objective [219,220), kill [220,222), victory [222,223) | kill [194,212), death [212,213), kill [213,216), kill [220,223) |
| 231.0 | victory [231,231.433) | victory [230,231.433) | death [224,226), kill [226,229), objective [229,230), combat [230,231) | kill [224,230) |

## Aggregated non-neutral timeline

| Start | End | Type | Mean winning relative score |
|---:|---:|---|---:|
| 0.000000 | 4.000000 | transition | 0.442407 |
| 4.000000 | 6.000000 | objective | 0.261897 |
| 6.000000 | 20.000000 | death | 0.423165 |
| 20.000000 | 32.000000 | victory | 0.312813 |
| 32.000000 | 34.000000 | objective | 0.305943 |
| 34.000000 | 40.000000 | kill | 0.286562 |
| 40.000000 | 41.000000 | victory | 0.259379 |
| 41.000000 | 43.000000 | kill | 0.234786 |
| 43.000000 | 49.000000 | victory | 0.276760 |
| 49.000000 | 50.000000 | objective | 0.267465 |
| 50.000000 | 52.000000 | victory | 0.277403 |
| 52.000000 | 56.000000 | death | 0.311889 |
| 56.000000 | 59.000000 | kill | 0.286535 |
| 59.000000 | 60.000000 | victory | 0.265500 |
| 60.000000 | 61.000000 | kill | 0.259861 |
| 61.000000 | 75.000000 | victory | 0.355128 |
| 75.000000 | 81.000000 | death | 0.373629 |
| 81.000000 | 85.000000 | combat | 0.289092 |
| 85.000000 | 87.000000 | kill | 0.282768 |
| 87.000000 | 93.000000 | victory | 0.374445 |
| 93.000000 | 96.000000 | death | 0.216370 |
| 96.000000 | 98.000000 | kill | 0.224373 |
| 98.000000 | 102.000000 | combat | 0.241716 |
| 102.000000 | 104.000000 | objective | 0.244019 |
| 104.000000 | 107.000000 | death | 0.248848 |
| 107.000000 | 113.000000 | kill | 0.268036 |
| 113.000000 | 116.000000 | victory | 0.269648 |
| 116.000000 | 122.000000 | kill | 0.316179 |
| 122.000000 | 123.000000 | combat | 0.248636 |
| 123.000000 | 125.000000 | objective | 0.262012 |
| 125.000000 | 127.000000 | death | 0.225949 |
| 127.000000 | 133.000000 | victory | 0.384910 |
| 133.000000 | 137.000000 | death | 0.282499 |
| 137.000000 | 138.000000 | victory | 0.223829 |
| 138.000000 | 139.000000 | kill | 0.224474 |
| 139.000000 | 141.000000 | victory | 0.229990 |
| 141.000000 | 146.000000 | death | 0.296135 |
| 146.000000 | 147.000000 | victory | 0.226203 |
| 147.000000 | 148.000000 | death | 0.230612 |
| 148.000000 | 150.000000 | victory | 0.272869 |
| 150.000000 | 151.000000 | death | 0.209361 |
| 151.000000 | 153.000000 | victory | 0.271198 |
| 153.000000 | 157.000000 | death | 0.280729 |
| 157.000000 | 166.000000 | victory | 0.402449 |
| 166.000000 | 170.000000 | kill | 0.254850 |
| 170.000000 | 175.000000 | death | 0.281679 |
| 175.000000 | 177.000000 | kill | 0.260041 |
| 177.000000 | 178.000000 | death | 0.230723 |
| 178.000000 | 190.000000 | kill | 0.279959 |
| 190.000000 | 192.000000 | death | 0.258501 |
| 192.000000 | 193.000000 | kill | 0.236784 |
| 193.000000 | 194.000000 | combat | 0.225701 |
| 194.000000 | 212.000000 | kill | 0.296268 |
| 212.000000 | 213.000000 | death | 0.218369 |
| 213.000000 | 216.000000 | kill | 0.266636 |
| 216.000000 | 220.000000 | combat | 0.346065 |
| 220.000000 | 223.000000 | kill | 0.275290 |
| 223.000000 | 224.000000 | death | 0.219645 |
| 224.000000 | 230.000000 | kill | 0.325027 |
| 230.000000 | 231.433288 | victory | 0.350102 |

## Limitations and reproduction

One already-edited video. Pretrained image-text evidence is not video understanding. A centered window uses up to two seconds of future context and can blur short events. Relative scores are uncalibrated; no accuracy or generalization claim, no overall winner. No retention, tuning, detector changes, or production clipping changes.
Run python evaluate_temporal_semantics.py from the repository. The runner refuses to overwrite its first comparison artifacts. All raw CLIP code/results remain unchanged.
Saved ignored outputs: output/temporal_clip_stability.json, output/temporal_clip_timeline.json, output/temporal_clip_events.json, output/temporal_clip_comparison.json.
