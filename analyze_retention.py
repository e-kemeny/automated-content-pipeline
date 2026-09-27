"""Descriptive report: python analyze_retention.py All.csv --annotations ground_truth_v2.json."""

import argparse
import math
from pathlib import Path
import sys

from retention import load_retention_csv, align_retention_with_v2

CONTEXT = ("Exploratory observations from ONE already-edited video. Absolute retention "
           "naturally changes over the timeline; these are not quality scores or "
           "directly comparable early/late baselines.")


def format_report(aligned):
    lines = [CONTEXT,
             "Beginning/end = first/last sample INSIDE [start, end); no interpolation.",
             "Retention in percent; change in percentage points (pp).", ""]
    for summary in aligned["summaries"]:
        annotation = summary["annotation"]
        lines.append(f"{annotation['start']:g}-{annotation['end']:g}s | {annotation['type']}")
        lines.append(f"  {annotation['description']}")
        if summary["sample_count"] == 0:
            lines.append("  Observations: 0 | No observations; statistics unavailable.")
        else:
            lines.append(
                f"  Observations: {summary['sample_count']} | Mean: {summary['mean_retention']:.2f}%"
                f" | Beginning: {summary['start_retention']:.2f}%"
                f" | Ending: {summary['end_retention']:.2f}%"
                f" | Change: {summary['retention_change']:+.2f} pp"
            )
    lines.append(f"\nUnassigned observations: {len(aligned['unassigned'])}")
    return "\n".join(lines)


def save_plot(rows, aligned, video_duration, output_path):
    # Lazy import: reports and non-visual tests do not require matplotlib.
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Patch

    ordered = sorted(rows, key=lambda row: row["timestamp_seconds"])
    values = [float(row["Absolute audience retention (%)"]) for row in ordered]
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Plot retention values must be finite numbers.")
    colors = dict(intro="#8da0cb", transition="#e5c494", combat="#66c2a5",
                  objective="#fc8d62", victory="#a6d854", other="#b3b3b3")
    fig, (ax, timeline) = plt.subplots(2, 1, figsize=(12, 6), sharex=True,
                                     gridspec_kw={"height_ratios": [5, 1]})
    try:
        ax.plot([row["timestamp_seconds"] for row in ordered], values,
                color="#253858", linewidth=1.7, label="Audience retention")
        if not ordered:
            ax.text(0.5, 0.5, "No retention observations", transform=ax.transAxes, ha="center")
        seen = []
        for index, group in enumerate(aligned["intervals"], start=1):
            annotation = group["annotation"]
            kind = annotation["type"]
            start, end = annotation["start"], annotation["end"]
            ax.axvspan(start, end, color=colors[kind], alpha=0.12)
            timeline.axvspan(start, end, color=colors[kind], alpha=0.85, ec="white")
            timeline.text((start + end) / 2, 0.5, str(index), ha="center", va="center", fontsize=8)
            if kind not in seen:
                seen.append(kind)
        ax.set_ylabel("Absolute audience retention (%)")
        ax.set_title("Audience retention with human-labeled V2 intervals")
        ax.grid(axis="y", alpha=0.25)
        ax.legend(loc="upper right")
        timeline.set_yticks([])
        timeline.set_ylabel("V2 interval")
        timeline.set_xlabel("Video timestamp (seconds)")
        timeline.set_xlim(0, video_duration)
        fig.legend(handles=[Patch(color=colors[kind], label=kind) for kind in seen],
                   loc="lower center", bbox_to_anchor=(0.5, 0.07), ncol=6, frameon=False)
        fig.text(0.5, 0.025, "One already-edited video; descriptive only. Absolute retention varies over the timeline.",
                 ha="center", fontsize=9)
        fig.tight_layout(rect=(0, 0.14, 1, 1))
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=150)
    finally:
        plt.close(fig)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("retention_csv", type=Path, help="Path to the YouTube All.csv export")
    parser.add_argument("--annotations", type=Path,
                        default=Path(__file__).resolve().with_name("ground_truth_v2.json"))
    parser.add_argument("--duration", type=float, default=231.433288, help="Video duration in seconds")
    parser.add_argument("--output", type=Path, default=Path("output/retention_analysis.png"))
    args = parser.parse_args(argv)
    try:
        rows = load_retention_csv(args.retention_csv, args.duration)
        aligned = align_retention_with_v2(rows, args.duration, args.annotations)
        print(format_report(aligned))
        save_plot(rows, aligned, args.duration, args.output)
        print(f"\nPlot saved: {args.output.resolve()}")
    except ModuleNotFoundError as error:
        if error.name != "matplotlib":
            raise
        print("Plot unavailable: matplotlib is not installed in this Python environment. "
              "Use an environment with matplotlib; no dependencies were changed.", file=sys.stderr)
        return 1
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"Analysis failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
