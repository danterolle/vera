"""Render charts for the expanded paired validation pack."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

matplotlib.rcParams["svg.hashsalt"] = "vera"

BASE = "#94a3b8"
ADAPTER = "#1d4ed8"
OVERLAP = "#d97706"
INK = "#1f2328"
MUTED = "#57606a"
GRID = "#e5e7eb"


def style(axis, grid="x"):
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d0d7de")
    axis.tick_params(colors=MUTED, labelsize=9)
    if grid == "x":
        axis.xaxis.grid(True, color=GRID, linewidth=0.8)
    else:
        axis.yaxis.grid(True, color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)


def heading(figure, title, subtitle):
    figure.text(0.01, 0.97, title, fontsize=13, fontweight="bold", color=INK, va="top")
    figure.text(0.01, 0.91, subtitle, fontsize=9, color=MUTED, va="top")
    figure.subplots_adjust(top=0.82, left=0.23, right=0.98, bottom=0.13)


def save(figure, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path, format="svg", metadata={"Date": None}, bbox_inches="tight", pad_inches=0.08,
    )
    path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(figure)


def strict_pass(rows: list[dict], model: str) -> float:
    selected = [row for row in rows if row["model"] == model]
    return sum(
        bool(row.get("schema_valid"))
        and row.get("out_of_scope_correct") is True
        and row.get("status_recall") == 1
        and row.get("validation_failures") == 0
        for row in selected
    ) / len(selected)


def overall_chart(path: Path, scores: dict) -> None:
    metrics = [
        ("JSON valid", "json_valid_rate"),
        ("VERA schema valid", "schema_valid_rate"),
        ("Scope correct", "scope_accuracy"),
        ("Claim-status recall", "mean_status_recall"),
        ("Citation clean", "citation_failure_rate"),
        ("Strict contract pass", "strict_pass"),
    ]
    rows = scores["results"]
    values = {}
    for model in ("base", "adapter"):
        overall = scores["models"][model]["overall"]
        values[model] = []
        for _, key in metrics:
            if key == "strict_pass":
                value = strict_pass(rows, model)
            elif key == "citation_failure_rate":
                value = 1 - overall[key]
            else:
                value = overall[key]
            values[model].append(value * 100)

    positions = list(range(len(metrics)))
    height = 0.36
    figure, axis = plt.subplots(figsize=(8.6, 4.7))
    heading(
        figure,
        "Paired validation: base vs step-400 adapter",
        "110 paired synthetic examples; status and citation rates use schema-valid answers",
    )
    for offset, model, color, label in (
        (-height / 2, "base", BASE, "Base"),
        (height / 2, "adapter", ADAPTER, "Adapter 400"),
    ):
        bars = axis.barh(
            [position + offset for position in positions], values[model], height,
            color=color, label=label,
        )
        axis.bar_label(bars, fmt="%.1f%%", padding=3, fontsize=8, color=INK)
    axis.set_yticks(positions, [label for label, _ in metrics], fontsize=9, color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, 115)
    axis.set_xticks([0, 25, 50, 75, 100])
    axis.set_xlabel("Rate", color=MUTED, fontsize=9)
    style(axis)
    axis.legend(frameon=False, ncol=2, loc="lower center",
                bbox_to_anchor=(0.5, 1.01), fontsize=9)
    save(figure, path)


def task_chart(path: Path, scores: dict) -> None:
    tasks = sorted(scores["models"]["base"]["by_task"])
    positions = list(range(len(tasks)))
    height = 0.36
    figure, axis = plt.subplots(figsize=(8.6, 5.7))
    heading(
        figure,
        "Schema-valid answers by task",
        "Ten examples per task; labels show valid answers out of ten",
    )
    for offset, model, color, label in (
        (-height / 2, "base", BASE, "Base"),
        (height / 2, "adapter", ADAPTER, "Adapter 400"),
    ):
        counts = [
            round(scores["models"][model]["by_task"][task]["schema_valid_rate"] * 10)
            for task in tasks
        ]
        bars = axis.barh(
            [position + offset for position in positions], counts, height,
            color=color, label=label,
        )
        axis.bar_label(bars, labels=[f"{count}/10" for count in counts],
                       padding=3, fontsize=8, color=INK)
    axis.set_yticks(positions, [task.replace("_", " ") for task in tasks], fontsize=8)
    axis.invert_yaxis()
    axis.set_xlim(0, 11.6)
    axis.set_xticks([0, 2, 4, 6, 8, 10])
    axis.set_xlabel("Schema-valid answers", color=MUTED, fontsize=9)
    style(axis)
    axis.legend(frameon=False, ncol=2, loc="lower center",
                bbox_to_anchor=(0.5, 1.01), fontsize=9)
    save(figure, path)


def overlap_chart(path: Path, pack: dict) -> None:
    total = pack["examples"]
    metrics = [
        ("Exact target seen in training", pack["target_seen_in_training"], OVERLAP),
        ("Duplicate target rows", pack["target_duplicate_rows_within_pack"], OVERLAP),
        ("Unique target strings", pack["target_unique_within_pack"], ADAPTER),
    ]
    positions = list(range(len(metrics)))
    figure, axis = plt.subplots(figsize=(8.6, 3.2))
    heading(
        figure,
        "Validation-pack target overlap",
        f"{total} selected cases; overlap and duplicate measures can intersect",
    )
    bars = axis.barh(
        positions, [value for _, value, _ in metrics],
        color=[color for _, _, color in metrics], height=0.52,
    )
    axis.bar_label(
        bars, labels=[f"{value}/{total}" for _, value, _ in metrics],
        padding=4, fontsize=9, color=INK,
    )
    axis.set_yticks(positions, [label for label, _, _ in metrics], fontsize=9, color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, total * 1.18)
    axis.set_xlabel("Cases / unique target strings", color=MUTED, fontsize=9)
    style(axis)
    save(figure, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--pack-report", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scores = json.loads(args.scores.read_text())
    pack = json.loads(args.pack_report.read_text())
    overall_chart(args.output / "overall.svg", scores)
    task_chart(args.output / "schema-by-task.svg", scores)
    overlap_chart(args.output / "target-overlap.svg", pack)


if __name__ == "__main__":
    main()
