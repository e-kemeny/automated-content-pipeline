# CLIP semantic V1: first pretrained semantic experiment

Model: openai/clip-vit-base-patch32; revision: 3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268.
Device: cpu (AMD64 Family 25 Model 117 Stepping 2, AuthenticAMD); PyTorch 2.13.0+cpu; Transformers 4.57.6; runtime including setup: 92.65s.
Video: 231.433288s; SHA-256: 6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09.

## Frozen protocol

1 frame/s on the 0,1,2,... < duration grid, using FFmpeg fps=1:start_time=0:round=up. Timestamps describe that resampled grid, not exact original frame PTS. No labels influence sampling.
Argmax across these seven prompts (ties use listed order); preserve all scaled CLIP logits as similarity and their seven-way softmax as zero_shot_score:

- combat: a Minecraft player fighting another player
- kill: a Minecraft player defeating another player
- death: a Minecraft death or respawn screen
- objective: a Minecraft player breaking an important objective
- transition: a Minecraft game transition or waiting screen
- victory: a Minecraft victory or win screen
- neutral: ordinary Minecraft gameplay with no major event

Each sample represents [t,min(t+1,duration)). Consecutive equal labels merge; neutral runs produce no event. No threshold, smoothing, or minimum duration. The interface's required confidence stores mean winning zero_shot_score, explicitly marked uncalibrated in metadata; underlying frame evidence is preserved.

## Counts and same-type GT coverage

| Type | Predicted events | GT intervals | Same-type covered / GT seconds |
|---|---:|---:|---|
| combat | 16 | 9 | 15.000000 / 172.000000 (8.72%) |
| kill | 37 | 0 | N/A (no GT intervals) |
| death | 27 | 0 | N/A (no GT intervals) |
| objective | 24 | 0 | N/A (no GT intervals) |
| transition | 4 | 2 | 2.000000 / 14.000000 (14.29%) |
| victory | 35 | 2 | 5.433000 / 26.433000 (20.55%) |
| intro | 0 | 1 | 0.000000 / 18.000000 (0.00%) |

## Temporal overlap matrix (seconds)

Rows are broad GT sequences; columns are predicted frame-event types. Off-diagonal overlap is descriptive, not necessarily a misclassification. Intro has no prompt counterpart; kill/death may occur within GT combat.

| GT type | combat | kill | death | objective | transition | victory |
|---|---:|---:|---:|---:|---:|---:|
| intro | 0.000000 | 0.000000 | 8.000000 | 4.000000 | 4.000000 | 2.000000 |
| transition | 0.000000 | 1.000000 | 0.000000 | 1.000000 | 2.000000 | 9.000000 |
| combat | 15.000000 | 54.000000 | 35.000000 | 25.000000 | 1.000000 | 42.000000 |
| victory | 5.000000 | 10.000000 | 4.000000 | 2.000000 | 0.000000 | 5.433000 |

## Observed label patterns

232 sampled frames produced 143 non-neutral event runs. Frame winners: combat=20, kill=65, death=48, objective=32, transition=7, victory=59, neutral=1.
Short alternating runs describe label instability, not verified gameplay events.
- Within GT intro, the largest different-label overlap is death: 8.000000s. This is a mismatch diagnostic, not proof of frame-level error.
- Within GT transition, the largest different-label overlap is victory: 9.000000s. This is a mismatch diagnostic, not proof of frame-level error.
- Within GT combat, the largest different-label overlap is kill: 54.000000s. This is a mismatch diagnostic, not proof of frame-level error.
- Within GT victory, the largest different-label overlap is kill: 10.000000s. This is a mismatch diagnostic, not proof of frame-level error.

## Predicted timeline (neutral included)

| Start | End | Label | Samples |
|---:|---:|---|---:|
| 0.000 | 4.000 | transition | 4 |
| 4.000 | 7.000 | objective | 3 |
| 7.000 | 8.000 | victory | 1 |
| 8.000 | 11.000 | death | 3 |
| 11.000 | 12.000 | victory | 1 |
| 12.000 | 16.000 | death | 4 |
| 16.000 | 17.000 | objective | 1 |
| 17.000 | 19.000 | death | 2 |
| 19.000 | 20.000 | neutral | 1 |
| 20.000 | 21.000 | objective | 1 |
| 21.000 | 24.000 | victory | 3 |
| 24.000 | 25.000 | kill | 1 |
| 25.000 | 26.000 | victory | 1 |
| 26.000 | 27.000 | transition | 1 |
| 27.000 | 31.000 | victory | 4 |
| 31.000 | 33.000 | objective | 2 |
| 33.000 | 34.000 | combat | 1 |
| 34.000 | 38.000 | kill | 4 |
| 38.000 | 39.000 | victory | 1 |
| 39.000 | 41.000 | kill | 2 |
| 41.000 | 43.000 | victory | 2 |
| 43.000 | 44.000 | objective | 1 |
| 44.000 | 45.000 | kill | 1 |
| 45.000 | 47.000 | victory | 2 |
| 47.000 | 49.000 | objective | 2 |
| 49.000 | 50.000 | victory | 1 |
| 50.000 | 51.000 | kill | 1 |
| 51.000 | 52.000 | objective | 1 |
| 52.000 | 53.000 | victory | 1 |
| 53.000 | 55.000 | death | 2 |
| 55.000 | 56.000 | kill | 1 |
| 56.000 | 58.000 | objective | 2 |
| 58.000 | 60.000 | kill | 2 |
| 60.000 | 62.000 | victory | 2 |
| 62.000 | 63.000 | kill | 1 |
| 63.000 | 65.000 | victory | 2 |
| 65.000 | 66.000 | death | 1 |
| 66.000 | 67.000 | combat | 1 |
| 67.000 | 68.000 | objective | 1 |
| 68.000 | 70.000 | victory | 2 |
| 70.000 | 71.000 | objective | 1 |
| 71.000 | 74.000 | victory | 3 |
| 74.000 | 76.000 | kill | 2 |
| 76.000 | 77.000 | victory | 1 |
| 77.000 | 80.000 | death | 3 |
| 80.000 | 81.000 | victory | 1 |
| 81.000 | 83.000 | combat | 2 |
| 83.000 | 84.000 | objective | 1 |
| 84.000 | 85.000 | kill | 1 |
| 85.000 | 86.000 | combat | 1 |
| 86.000 | 87.000 | kill | 1 |
| 87.000 | 88.000 | victory | 1 |
| 88.000 | 89.000 | kill | 1 |
| 89.000 | 91.000 | victory | 2 |
| 91.000 | 94.000 | death | 3 |
| 94.000 | 95.000 | objective | 1 |
| 95.000 | 96.000 | kill | 1 |
| 96.000 | 97.000 | victory | 1 |
| 97.000 | 99.000 | death | 2 |
| 99.000 | 100.000 | combat | 1 |
| 100.000 | 101.000 | victory | 1 |
| 101.000 | 104.000 | objective | 3 |
| 104.000 | 105.000 | death | 1 |
| 105.000 | 106.000 | kill | 1 |
| 106.000 | 107.000 | death | 1 |
| 107.000 | 108.000 | victory | 1 |
| 108.000 | 112.000 | kill | 4 |
| 112.000 | 113.000 | death | 1 |
| 113.000 | 114.000 | objective | 1 |
| 114.000 | 116.000 | victory | 2 |
| 116.000 | 121.000 | kill | 5 |
| 121.000 | 122.000 | death | 1 |
| 122.000 | 123.000 | objective | 1 |
| 123.000 | 125.000 | combat | 2 |
| 125.000 | 126.000 | objective | 1 |
| 126.000 | 127.000 | kill | 1 |
| 127.000 | 129.000 | death | 2 |
| 129.000 | 134.000 | victory | 5 |
| 134.000 | 136.000 | death | 2 |
| 136.000 | 138.000 | kill | 2 |
| 138.000 | 139.000 | transition | 1 |
| 139.000 | 140.000 | victory | 1 |
| 140.000 | 141.000 | combat | 1 |
| 141.000 | 142.000 | death | 1 |
| 142.000 | 143.000 | kill | 1 |
| 143.000 | 144.000 | death | 1 |
| 144.000 | 145.000 | objective | 1 |
| 145.000 | 146.000 | death | 1 |
| 146.000 | 147.000 | kill | 1 |
| 147.000 | 148.000 | victory | 1 |
| 148.000 | 149.000 | death | 1 |
| 149.000 | 150.000 | objective | 1 |
| 150.000 | 151.000 | victory | 1 |
| 151.000 | 152.000 | death | 1 |
| 152.000 | 154.000 | victory | 2 |
| 154.000 | 157.000 | death | 3 |
| 157.000 | 158.000 | kill | 1 |
| 158.000 | 160.000 | victory | 2 |
| 160.000 | 161.000 | transition | 1 |
| 161.000 | 166.000 | victory | 5 |
| 166.000 | 167.000 | combat | 1 |
| 167.000 | 169.000 | kill | 2 |
| 169.000 | 170.000 | combat | 1 |
| 170.000 | 173.000 | death | 3 |
| 173.000 | 175.000 | kill | 2 |
| 175.000 | 176.000 | death | 1 |
| 176.000 | 178.000 | kill | 2 |
| 178.000 | 179.000 | combat | 1 |
| 179.000 | 181.000 | death | 2 |
| 181.000 | 182.000 | combat | 1 |
| 182.000 | 186.000 | kill | 4 |
| 186.000 | 188.000 | objective | 2 |
| 188.000 | 189.000 | kill | 1 |
| 189.000 | 191.000 | death | 2 |
| 191.000 | 192.000 | combat | 1 |
| 192.000 | 193.000 | death | 1 |
| 193.000 | 194.000 | objective | 1 |
| 194.000 | 195.000 | kill | 1 |
| 195.000 | 196.000 | victory | 1 |
| 196.000 | 199.000 | kill | 3 |
| 199.000 | 200.000 | objective | 1 |
| 200.000 | 201.000 | kill | 1 |
| 201.000 | 202.000 | objective | 1 |
| 202.000 | 204.000 | kill | 2 |
| 204.000 | 205.000 | combat | 1 |
| 205.000 | 206.000 | victory | 1 |
| 206.000 | 209.000 | kill | 3 |
| 209.000 | 210.000 | combat | 1 |
| 210.000 | 211.000 | victory | 1 |
| 211.000 | 212.000 | kill | 1 |
| 212.000 | 213.000 | victory | 1 |
| 213.000 | 214.000 | kill | 1 |
| 214.000 | 215.000 | death | 1 |
| 215.000 | 216.000 | kill | 1 |
| 216.000 | 219.000 | combat | 3 |
| 219.000 | 220.000 | objective | 1 |
| 220.000 | 222.000 | kill | 2 |
| 222.000 | 223.000 | victory | 1 |
| 223.000 | 224.000 | kill | 1 |
| 224.000 | 226.000 | death | 2 |
| 226.000 | 229.000 | kill | 3 |
| 229.000 | 230.000 | objective | 1 |
| 230.000 | 231.000 | combat | 1 |
| 231.000 | 231.433 | victory | 1 |

## Frozen candidate diagnostics

Point association, inclusive 5-second distance to event extent. Overlap and additional nearby events are separate. No score changes.

- Audio-only — Top 5: 40, 69, 84, 146, 170
- Audio-only — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217
- Audio + Scene — Top 5: 40, 69, 84, 122, 170
- Audio + Scene — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217
- Audio + Motion — Top 5: 69, 84, 146, 170, 231
- Audio + Motion — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 231

| Candidate | Overlapping events | Additional nearby events | Max relative evidence by type |
|---:|---|---|---|
| 18.0 | death [17,19) | death [12,16), objective [16,17), objective [20,21), victory [21,24) | death=0.5444, objective=0.3795, victory=0.3769 |
| 40.0 | kill [39,41) | kill [34,38), victory [38,39), victory [41,43), objective [43,44), kill [44,45), victory [45,47) | kill=0.3140, objective=0.2296, victory=0.3979 |
| 69.0 | victory [68,70) | victory [63,65), death [65,66), combat [66,67), objective [67,68), objective [70,71), victory [71,74), kill [74,76) | combat=0.3941, kill=0.4265, death=0.3359, objective=0.4424, victory=0.5488 |
| 84.0 | kill [84,85) | death [77,80), victory [80,81), combat [81,83), objective [83,84), combat [85,86), kill [86,87), victory [87,88), kill [88,89), victory [89,91) | combat=0.3932, kill=0.3097, death=0.5939, objective=0.3518, victory=0.7606 |
| 103.0 | objective [101,104) | death [97,99), combat [99,100), victory [100,101), death [104,105), kill [105,106), death [106,107), victory [107,108), kill [108,112) | combat=0.4195, kill=0.3361, death=0.4112, objective=0.3327, victory=0.3538 |
| 122.0 | objective [122,123) | kill [116,121), death [121,122), combat [123,125), objective [125,126), kill [126,127), death [127,129) | combat=0.3084, kill=0.3966, death=0.4247, objective=0.6432 |
| 146.0 | kill [146,147) | combat [140,141), death [141,142), kill [142,143), death [143,144), objective [144,145), death [145,146), victory [147,148), death [148,149), objective [149,150), victory [150,151), death [151,152) | combat=0.4013, kill=0.3076, death=0.6715, objective=0.3883, victory=0.5741 |
| 170.0 | death [170,173) | victory [161,166), combat [166,167), kill [167,169), combat [169,170), kill [173,175), death [175,176) | combat=0.4102, kill=0.2928, death=0.4257, victory=0.4908 |
| 192.0 | death [192,193) | objective [186,188), kill [188,189), death [189,191), combat [191,192), objective [193,194), kill [194,195), victory [195,196), kill [196,199) | combat=0.4215, kill=0.4290, death=0.3417, objective=0.3156, victory=0.4827 |
| 217.0 | combat [216,219) | kill [211,212), victory [212,213), kill [213,214), death [214,215), kill [215,216), objective [219,220), kill [220,222), victory [222,223) | combat=0.4436, kill=0.3652, death=0.4057, objective=0.3011, victory=0.5673 |
| 231.0 | victory [231,231.433) | death [224,226), kill [226,229), objective [229,230), combat [230,231) | combat=0.2986, kill=0.4950, death=0.4121, objective=0.2966, victory=0.9187 |

## Interpretation limits

Pretrained by OpenAI, not trained or fine-tuned by this project. CLIP is a frame-level image-text model, not true video understanding. Zero-shot scores are relative similarities, not calibrated probabilities or factual confidence. A forced seven-way choice is not reliable event verification. Broad human intervals and frame events have different granularity; no conventional accuracy is claimed. This is one already-edited Minecraft video, with no generalization claim. No prompts, sampling, conversion, ranking, or clipping were tuned against these annotations.

Reference: https://huggingface.co/docs/transformers/en/model_doc/clip

Reproduce inference: python semantic_clip.py (refuses to overwrite existing results).
Regenerate this report without inference: python evaluate_semantic_clip.py.
Raw artifacts: output/clip_semantic_timeline.json and output/clip_semantic_events.json (ignored).
Install optional dependencies with python -m pip install -r requirements-clip.txt. This run used output/clip_env/Scripts/python.exe, an isolated environment inheriting the existing CPU PyTorch. CUDA was unavailable in that build despite an NVIDIA GPU being installed. Model cache and frames are under output/. The downloader used ordinary HTTP because optional hf_xet was absent.
