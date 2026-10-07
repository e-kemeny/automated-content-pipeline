# Multiframe semantic V1

All responses failed the frozen label format. No semantic events were accepted. Zero coverage is an output-contract failure, not evidence that gameplay events were absent. The 1.0 adjacent-state fraction is repeated INVALID state, not semantic stability. This run cannot establish whether multiframe context improves semantic correctness.

Model: HuggingFaceTB/SmolVLM2-256M-Video-Instruct; revision 067788b187b95ebe7b2e040b3e4299e342e5b8fd.
Selected as a small pretrained 256M-parameter model supporting multi-image input in maintained Transformers. Runs locally with standard eager attention and float32, no paid API, training, or FlashAttention requirement. The existing CPU PyTorch environment was reused.
Sources: https://huggingface.co/HuggingFaceTB/SmolVLM2-256M-Video-Instruct and https://huggingface.co/docs/transformers/v4.57.1/en/model_doc/smolvlm

## Frozen experiment

Non-overlapping [0,5), [5,10), ... windows, final window truncated to video duration. Three frames at start, midpoint, and end-min(0.1,span/10) seconds, extracted with FFmpeg seek. Timestamps are requested seek positions. RGB frames fit inside 512x512 preserving aspect ratio; processor image splitting disabled. All three images and their timestamps enter ONE chat context and ONE generation call, independently for each window.
Greedy generation, one beam, at most 48 new tokens. No retries or label correction. Parse first nonempty line as exactly one vocabulary label, optionally preceded by 'label:', case-insensitively. Any other response remains invalid; it is not converted to neutral. Remaining lines are evidence, retained verbatim. Neutral/invalid windows produce no event; adjacent identical valid labels merge, with all original window responses in metadata.
Confidence is unavailable: semantic-event confidence=0.0 is ONLY a schema compatibility sentinel. Metadata stores confidence_available=false and model_confidence=null. No score is inferred from text.

Exact instruction:

These three Minecraft gameplay frames are in chronological order from one short interval. Examine them together. Choose the single best description of the interval: combat (players fighting), kill (a player defeated), death (the viewpoint player dies or respawns), objective (an important gameplay objective is acted on), transition (waiting or changing scenes), victory (a win), or neutral (ordinary gameplay with no major event). On the first line output only one of these labels: combat, kill, death, objective, transition, victory, neutral. On the second line give one short sentence of visible evidence. Do not give a confidence score.

## Runtime

Device: cpu; hardware: AMD64 Family 25 Model 117 Stepping 2, AuthenticAMD; torch 2.13.0+cpu; transformers 4.57.6.
Video duration 231.433288s; video SHA-256 6f96698e4325e8126f8348069dc620d23d5af2f208696dcc40b61ae8c4871b09.
47 windows. Model setup/loading: 17.992s; frame extraction: 75.841s; inference including preprocessing: 469.814s; total measured run: 564.849s.
Inference throughput: 0.100039 windows/s; source duration / inference time: 0.4926x realtime.
Invalid responses: 47; neutral windows: 0.

## Fragmentation comparison

For adjacent-label stability, window labels are projected onto the unchanged 1 FPS grid; invalid/missing windows remain None (a distinct state). Durations use actual merged event bounds. Five-second classification structurally limits switching; lower fragmentation does not itself demonstrate temporal understanding or better semantics.

| Metric | Raw CLIP | Temporal CLIP | Multiframe |
|---|---:|---:|---:|
| event_count | 143.000000 | 60.000000 | 0.000000 |
| label_transitions | 143.000000 | 59.000000 | 0.000000 |
| mean_event_duration | 1.611422 | 3.857221 | N/A |
| median_event_duration | 1.000000 | 2.500000 | N/A |
| longest_event_duration | 5.000000 | 18.000000 | N/A |
| adjacent_same_label_fraction | 0.380952 | 0.744589 | 1.000000 |

## Counts and same-type GT coverage

| Type | Raw events | Temporal events | Multiframe events | GT seconds | Raw / temporal / multiframe covered seconds |
|---|---:|---:|---:|---:|---|
| combat | 16 | 5 | 0 | 172.000000 | 15.000000 / 10.000000 / 0.000000 |
| kill | 37 | 17 | 0 | N/A | N/A |
| death | 27 | 16 | 0 | N/A | N/A |
| objective | 24 | 5 | 0 | N/A | N/A |
| transition | 4 | 1 | 0 | 14.000000 | 2.000000 / 0.000000 / 0.000000 |
| victory | 35 | 16 | 0 | 26.433000 | 5.433000 / 6.433000 / 0.000000 |
| intro | 0 | 0 | 0 | 18.000000 | 0.000000 / 0.000000 / 0.000000 |

## Overlap matrix (seconds)

Each cell is raw / temporal / multiframe. Different-label overlap is not conventional accuracy: GT describes broad sequences, and kills/deaths may be inside combat; intro has no model class.

| GT type | combat | kill | death | objective | transition | victory |
|---|---:|---:|---:|---:|---:|---:|
| combat | 15.000000 / 10.000000 / 0.000000 | 54.000000 / 64.000000 / 0.000000 | 35.000000 / 41.000000 / 0.000000 | 25.000000 / 7.000000 / 0.000000 | 1.000000 / 0.000000 / 0.000000 | 42.000000 / 50.000000 / 0.000000 |
| intro | 0.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | 8.000000 / 12.000000 / 0.000000 | 4.000000 / 2.000000 / 0.000000 | 4.000000 / 4.000000 / 0.000000 | 2.000000 / 0.000000 / 0.000000 |
| transition | 0.000000 / 0.000000 / 0.000000 | 1.000000 / 0.000000 / 0.000000 | 0.000000 / 1.000000 / 0.000000 | 1.000000 / 0.000000 / 0.000000 | 2.000000 / 0.000000 / 0.000000 | 9.000000 / 13.000000 / 0.000000 |
| victory | 5.000000 / 4.000000 / 0.000000 | 10.000000 / 14.000000 / 0.000000 | 4.000000 / 2.000000 / 0.000000 | 2.000000 / 0.000000 / 0.000000 | 0.000000 / 0.000000 / 0.000000 | 5.433000 / 6.433000 / 0.000000 |

## Frozen candidates and changed interpretations

Same point candidates and inclusive 5-second event-distance association. No scoring changes; confidence sentinels must not be compared to CLIP relative scores.

- Audio + Motion — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 231
- Audio + Motion — Top 5: 69, 84, 146, 170, 231
- Audio + Scene — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217
- Audio + Scene — Top 5: 40, 69, 84, 122, 170
- Audio-only — Top 10: 18, 40, 69, 84, 103, 122, 146, 170, 192, 217
- Audio-only — Top 5: 40, 69, 84, 146, 170

| Candidate | Raw overlap | Temporal overlap | Multiframe overlap | Multiframe nearby |
|---:|---|---|---|---|
| 103.0 | objective [101,104) | objective [102,104) | none | none |
| 122.0 | objective [122,123) | combat [122,123) | none | none |
| 146.0 | kill [146,147) | victory [146,147) | none | none |
| 170.0 | death [170,173) | death [170,175) | none | none |
| 18.0 | death [17,19) | death [6,20) | none | none |
| 192.0 | death [192,193) | kill [192,193) | none | none |
| 217.0 | combat [216,219) | combat [216,220) | none | none |
| 231.0 | victory [231,231.433) | victory [230,231.433) | none | none |
| 40.0 | kill [39,41) | victory [40,41) | none | none |
| 69.0 | victory [68,70) | victory [61,75) | none | none |
| 84.0 | kill [84,85) | combat [81,85) | none | none |

## Original model responses

These are model statements, not verified descriptions. Candidate-table changes above and these reasons provide qualitative examples; this design changes the model as well as input context, so it cannot isolate the causal benefit of multiple frames.

| Window | Frames | Parsed label | Original response |
|---|---|---|---|
| 0-5 | 0.000000, 2.500000, 4.900000 | INVALID |  The video shows a Minecraft game where a player is fighting against a group of enemies. The player is using a sword to attack the enemies, and the enemy is trying to escape. The player is trying to kill the enemy, but they are |
| 5-10 | 5.000000, 7.500000, 9.900000 | INVALID |  The video shows a scene from a Minecraft game where a player is fighting against a zombie. The player is wearing a white shirt and a blue hat, and they are surrounded by zombies. The zombie is wearing a white shirt and a blue |
| 10-15 | 10.000000, 12.500000, 14.900000 | INVALID |  The video shows a Minecraft game where a player is fighting against a zombie. The player is wearing a white shirt and a blue hat, and they are fighting against a zombie with a red face. The zombie is wearing a white shirt and a |
| 15-20 | 15.000000, 17.500000, 19.900000 | INVALID |  The video shows a scene from the game Minecraft where a player is fighting against a zombie. The player is wearing a white shirt and a blue hat, and they are surrounded by zombies. The zombie is wearing a white shirt and a blue |
| 20-25 | 20.000000, 22.500000, 24.900000 | INVALID |  The game is called "Game One" and the player is trying to kill a shark. The player is trying to kill the shark by using a sword and a shield. The player is trying to kill the shark by using a sword and a |
| 25-30 | 25.000000, 27.500000, 29.900000 | INVALID |  The first frame shows a player in a Minecraft-like environment, surrounded by blocks and a few other players. The player is holding a sword and appears to be in a combat mode, with the player's health bar showing 500 |
| 30-35 | 30.000000, 32.500000, 34.900000 | INVALID |  The video shows a player in a Minecraft game, who is fighting against a group of enemies. The player is using a sword to attack the enemies, and the enemy is trying to escape. The player is trying to kill the enemy, but |
| 35-40 | 35.000000, 37.500000, 39.900000 | INVALID |  The first frame shows a player in a red and white outfit fighting a large, red, armored creature. The player is in a fighting stance, with their right hand raised and their left hand on their hip. The creature has a large, |
| 40-45 | 40.000000, 42.500000, 44.900000 | INVALID |  "I love the bed" |
| 45-50 | 45.000000, 47.500000, 49.900000 | INVALID |  The video shows a player in a Minecraft game, who is fighting against a blue block. The player is using a sword to attack the blue block, which is located in the center of the screen. The player is using a sword to attack |
| 50-55 | 50.000000, 52.500000, 54.900000 | INVALID |  The video shows a player in a Minecraft game, who is in the middle of a battle with a player in a different game. The player in the first game is wearing a blue shirt and a helmet, while the player in the second game |
| 55-60 | 55.000000, 57.500000, 59.900000 | INVALID |  The video shows a player in a Minecraft game, who is in the middle of a battle. The player is surrounded by enemies, and the player is trying to get out of the way of the enemy. The player is trying to get out |
| 60-65 | 60.000000, 62.500000, 64.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a blue sky and a few clouds in the background. The player is holding a sword and is in the middle of a battle, with a large stone structure in the foreground. The |
| 65-70 | 65.000000, 67.500000, 69.900000 | INVALID |  The video shows a player in a Minecraft game, who is standing on a platform with a blue sky and a white cloud in the background. The player is holding a sword and is ready to attack. The player is surrounded by enemies, and |
| 70-75 | 70.000000, 72.500000, 74.900000 | INVALID |  The video shows a player in a Minecraft game, who is fighting against another player. The player is using a sword to attack the other player, who is trying to defend himself. The player is using a sword to attack the other player, |
| 75-80 | 75.000000, 77.500000, 79.900000 | INVALID |  The video shows a player in a Minecraft game, who is in the middle of a battle with another player. The player is in a state of combat, with the enemy player attempting to attack the player. The player is in a state of |
| 80-85 | 80.000000, 82.500000, 84.900000 | INVALID |  The game "BED DESTROYED!" is played in Minecraft. The player is fighting against a group of enemies, and the objective is to kill them. The player is also trying to kill a player who is defeated, and |
| 85-90 | 85.000000, 87.500000, 89.900000 | INVALID |  The first frame shows a player in a Minecraft-like environment, with a blue island in the background. The player is holding a sword and appears to be in the middle of a battle. The second frame shows a player in a Minecraft- |
| 90-95 | 90.000000, 92.500000, 94.900000 | INVALID |  The game's first frame shows a player in a blue outfit with a red helmet and a red and white outfit with a blue helmet, standing in front of a building with a sign that says "The Village". The player is holding a sword |
| 95-100 | 95.000000, 97.500000, 99.900000 | INVALID |  The first frame shows a player in a Minecraft environment, engaged in combat with another player. The player is using a sword to attack, and the enemy is defending with a shield. The player is in a state of combat, with the enemy |
| 100-105 | 100.000000, 102.500000, 104.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a character in a blue outfit and a character in a red outfit. The player is fighting against a group of enemies, and the environment is a dark, smoky environment with a few |
| 105-110 | 105.000000, 107.500000, 109.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a character in a red shirt and blue pants. The player is fighting against a group of enemies, and the environment is filled with blocks and other objects. The player is using a |
| 110-115 | 110.000000, 112.500000, 114.900000 | INVALID |  The first frame shows a player in a Minecraft environment, engaged in combat with a pink creature. The player's health is high, and they are using a health meter to keep track of their health. The environment is a simple, unad |
| 115-120 | 115.000000, 117.500000, 119.900000 | INVALID |  The first frame shows a player in a Minecraft environment, fighting against a group of enemies. The player is using a sword to attack the enemies, and the enemy is trying to escape. The player is also using a shield to protect themselves from |
| 120-125 | 120.000000, 122.500000, 124.900000 | INVALID |  The first frame shows a player in a Minecraft-like environment, with a character in the foreground and a character in the background. The player is holding a sword and appears to be in a combat mode, with the character in the background holding |
| 125-130 | 125.000000, 127.500000, 129.900000 | INVALID |  The video shows a player in a Minecraft game, who is in the middle of a battle with a group of enemies. The player is surrounded by a group of enemies, and the player is trying to escape. The player is trying to escape |
| 130-135 | 130.000000, 132.500000, 134.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a green block in the foreground and a white block in the background. The player is in a state of combat, with the green block blocking their path and the white block blocking their |
| 135-140 | 135.000000, 137.500000, 139.900000 | INVALID |  The first frame shows a player in a Minecraft environment, engaged in combat with another player. The player is using a sword to attack, and the enemy is defending with a shield. The player is in a state of combat, with the enemy |
| 140-145 | 140.000000, 142.500000, 144.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a character in a blue outfit and a character in a red outfit. The player is fighting against a group of enemies, and the environment is dark and gritty. The player is |
| 145-150 | 145.000000, 147.500000, 149.900000 | INVALID |  The first frame shows a player in a Minecraft game, with a character in a red shirt and blue pants. The player is in a room with a computer monitor in the background, and there are several other players in the room, some of |
| 150-155 | 150.000000, 152.500000, 154.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a green screen and a minimap. The player is in a room with a bed, a desk, and a computer monitor. The minimap shows a player in a room with |
| 155-160 | 155.000000, 157.500000, 159.900000 | INVALID |  The game's first frame is a combat scene where players fight against a large, green, glowing entity. |
| 160-165 | 160.000000, 162.500000, 164.900000 | INVALID |  The game's first frame shows a player in a Minecraft-like environment, with a character in the foreground and a player in the background. The player is holding a sword and appears to be in a fighting stance. The player's health bar |
| 165-170 | 165.000000, 167.500000, 169.900000 | INVALID |  The first frame shows a player in a Minecraft game, with a red block in the foreground and a purple background. The player is holding a sword and appears to be in a battle with another player. The player is wearing a helmet and has |
| 170-175 | 170.000000, 172.500000, 174.900000 | INVALID |  The first frame shows a player in a red and white outfit fighting a player in a blue outfit. The player in the red outfit is holding a gun and is surrounded by enemies. The player in the blue outfit is also holding a gun and |
| 175-180 | 175.000000, 177.500000, 179.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a purple background and a character with a face mask. The player is in a room with a bed, a table, and a computer monitor. The player is holding a gun and |
| 180-185 | 180.000000, 182.500000, 184.900000 | INVALID |  The first frame shows a player in a futuristic outfit, wearing headphones and a headset, standing in a futuristic setting with a purple background. The player is holding a gun and appears to be in a combat situation. The second frame shows a |
| 185-190 | 185.000000, 187.500000, 189.900000 | INVALID |  The first frame shows a player in a Minecraft game, with a character in a red outfit and a character in a blue outfit. The player is fighting against a group of enemies, and the player is using a sword to attack. The player |
| 190-195 | 190.000000, 192.500000, 194.900000 | INVALID |  The first frame shows a player in a red and white outfit fighting a large, dark creature with glowing red eyes. The creature has a large, gaping mouth and sharp teeth. The player is fighting with a sword, and the creature is |
| 195-200 | 195.000000, 197.500000, 199.900000 | INVALID |  The first frame shows a player in a blue outfit fighting a green monster in a cave. The player is in a fighting stance, with their left hand on the monster's back and their right hand on the ground. The background is a cave |
| 200-205 | 200.000000, 202.500000, 204.900000 | INVALID |  The first frame shows a player in a Minecraft-like environment, with a character in a purple outfit and a character in a blue outfit. The player is fighting against a group of enemies, and the environment is dark and gritty. The |
| 205-210 | 205.000000, 207.500000, 209.900000 | INVALID |  The first frame shows a player in a red and white outfit running through a dark room with a purple wall in the background. The player is wearing headphones and appears to be in a hurry. The second frame shows a player in a blue outfit |
| 210-215 | 210.000000, 212.500000, 214.900000 | INVALID |  A screenshot of a Minecraft game showing a player in a room with a purple wall and a window. The player is holding a gun and is aiming at a target on the wall. The player is wearing a helmet and has headphones on. The |
| 215-220 | 215.000000, 217.500000, 219.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a blue character in the foreground. The player is holding a sword and appears to be in a fighting stance. The background is a dark, pixelated landscape with a purple sky and |
| 220-225 | 220.000000, 222.500000, 224.900000 | INVALID |  The first frame shows a player in a Minecraft-like environment, with a character in a yellow outfit and a character in a blue outfit. The player is in a fighting stance, with their left hand on their hip and their right hand extended |
| 225-230 | 225.000000, 227.500000, 229.900000 | INVALID |  The first frame shows a player in a Minecraft environment, with a purple background and a character with a red glowing face. The player is in a fighting stance, with their right hand raised and their left hand on their hip. The environment is |
| 230-231.433 | 230.000000, 230.716644, 231.333288 | INVALID |  The first frame shows a player in a Minecraft environment, with a purple and yellow background, and a character with a red and white outfit. The player is in a fighting stance, with their right hand raised and their left hand on their hip |

## Limitations and reproduction

One already-edited Minecraft video; no generalization claim. Pretrained model, no fine-tuning. Three snapshots can miss an event or hallucinate a narrative. Model reasons are not proof. No ranking, weights, production boundaries/clipping, GT, or previous experiments changed. No tuning after GT comparison; no second model or Multiframe V2 attempted.
Environment: output/clip_env/Scripts/python.exe. Inference: python multiframe_semantics.py; evaluation: python evaluate_multiframe_semantics.py. Inference refuses to overwrite first-run artifacts. Outputs are ignored under output/multiframe_semantic_*.json and the per-window .jsonl journal.
Optional dependencies are pinned in requirements-multiframe.txt. Processor preflight required torchvision 0.28.0 and num2words 0.5.14. Image splitting was corrected and verified on synthetic inputs before real inference; no experiment parameters or parser rules changed after evaluation.
