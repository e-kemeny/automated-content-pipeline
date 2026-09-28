# Audience-retention case study

## Context and method

This exploratory analysis covers **one already-edited Minecraft BedWars video**, approximately **256K views**, with a duration of **231.433288 seconds** (about 3:52). Ground Truth V2 contains **14 human-annotated semantic intervals** describing content in the video.

The real YouTube `All.csv` export was loaded with the existing retention functions. Video-position percentages were converted to seconds and associated with V2 intervals using `[start, end)` boundaries. Intentional gaps remain unassigned; annotation boundaries were not extended. Beginning and ending retention are the first and last observed samples inside each interval, without interpolation. Mean retention is the unweighted sample mean; change is ending minus beginning in percentage points (pp).

Audience retention describes viewer behavior. It is **not ground truth or a quality score**. Absolute retention naturally changes over the timeline, so early and late absolute values should not be directly ranked. These observations do not establish causation, semantic-type superiority, or generalization to other videos.

## Interval results

Values below reproduce the analysis report, rounded to two decimal places. Intervals remain in chronological order.

| Interval (s) | Type | Mean | Beginning | Ending | Change (pp) | Observations |
|---|---|---:|---:|---:|---:|---:|
| 0-18 | intro | 52.51% | 93.98% | 43.64% | -50.34 | 8 |
| 19-27 | transition | 57.05% | 56.03% | 58.45% | +2.42 | 3 |
| 27-33 | combat | 54.06% | 54.34% | 52.14% | -2.20 | 3 |
| 33-47 | combat | 47.60% | 52.09% | 42.38% | -9.71 | 6 |
| 47-53 | combat | 40.16% | 41.01% | 39.30% | -1.71 | 2 |
| 53-76 | combat | 31.55% | 35.51% | 29.16% | -6.35 | 10 |
| 76-85 | combat | 28.62% | 29.42% | 28.69% | -0.73 | 4 |
| 85-92 | victory | 35.03% | 31.71% | 39.34% | +7.63 | 3 |
| 92-122 | combat | 32.32% | 40.28% | 24.63% | -15.65 | 13 |
| 122-158 | combat | 20.21% | 24.00% | 22.20% | -1.80 | 16 |
| 158-164 | transition | 25.23% | 24.47% | 26.00% | +1.53 | 2 |
| 164-192 | combat | 22.44% | 25.90% | 18.68% | -7.22 | 12 |
| 192-212 | combat | 16.31% | 18.56% | 14.29% | -4.27 | 9 |
| 212-231.433 | victory | 11.74% | 13.45% | 9.90% | -3.55 | 8 |

**Unassigned observations: 1.** No detector, weights, selection rules, or annotations were changed for this analysis.

## Reproduce locally

From the repository root, with the original export present:

```powershell
python analyze_retention.py "Audience retention 3 New BEST 16x Bedwars Texture Packs/All.csv" --annotations ground_truth_v2.json --duration 231.433288
```

The script prints the interval report and saves the plot to `output/retention_analysis.png`. The raw export directory and generated `output/` files are Git-ignored; this document records the descriptive results without committing those artifacts.
