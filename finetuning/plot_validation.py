"""Render strict-pass and cost charts for the paired validation pack."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

matplotlib.rcParams["svg.hashsalt"] = "vera"

BASE = "#94a3b8"
ADAPTER = "#1d4ed8"
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


def save(figure, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path, format="svg", metadata={"Date": None}, bbox_inches="tight", pad_inches=0.08,
    )
    path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(figure)


def strict(rows, model, task):
    selected = [row for row in rows if row["model"] == model and row["task"] == task]
    passed = sum(
        bool(row.get("schema_valid"))
        and row.get("out_of_scope_correct") is True
        and row.get("status_recall") == 1
        and row.get("validation_failures") == 0
        for row in selected
    )
    return passed, len(selected)


def strict_chart(path, scores):
    rows = scores["results"]
    tasks = sorted(scores["models"]["base"]["by_task"])
    positions = list(range(len(tasks)))
    height = 0.36
    figure, axis = plt.subplots(figsize=(8.6, 5.7))
    heading(
        figure,
        "Strict contract pass by task",
        "Schema valid, correct scope, full status coverage and no validator error",
    )
    figure.subplots_adjust(top=0.84, left=0.23, right=0.98, bottom=0.12)
    for offset, model, color, label in (
        (-height / 2, "base", BASE, "Base"),
        (height / 2, "adapter", ADAPTER, "Adapter 400"),
    ):
        counts = [strict(rows, model, task)[0] for task in tasks]
        bars = axis.barh(
            [position + offset for position in positions], counts, height,
            color=color, label=label,
        )
        totals = {strict(rows, model, task)[1] for task in tasks}
        total = totals.pop() if len(totals) == 1 else 10
        axis.bar_label(bars, labels=[f"{count}/{total}" for count in counts],
                       padding=3, fontsize=8, color=INK)
    axis.set_yticks(positions, [task.replace("_", " ") for task in tasks], fontsize=8)
    axis.invert_yaxis()
    axis.set_xlim(0, 11.6)
    axis.set_xticks([0, 2, 4, 6, 8, 10])
    axis.set_xlabel("Strict passes", color=MUTED, fontsize=9)
    style(axis)
    axis.legend(frameon=False, ncol=2, loc="lower center",
                bbox_to_anchor=(0.5, 1.01), fontsize=9)
    save(figure, path)


def cost_chart(path, scores):
    models = (("base", BASE, "Base"), ("adapter", ADAPTER, "Adapter 400"))
    panels = (
        ("Mean output tokens", "mean_output_tokens", "{:.0f}"),
        ("Mean seconds per answer", "mean_seconds", "{:.1f}"),
    )
    figure, axes = plt.subplots(1, 2, figsize=(8.6, 3.4))
    heading(
        figure,
        "Answer cost on the validation pack",
        "Greedy decoding, 768-token cap, identical prompts for base and adapter",
    )
    figure.subplots_adjust(top=0.74, left=0.08, right=0.98, bottom=0.16, wspace=0.32)
    for axis, (title, key, fmt) in zip(axes, panels, strict=True):
        values = [scores["models"][model]["overall"][key] for model, _, _ in models]
        bars = axis.bar(
            [0, 1], values, width=0.55,
            color=[color for _, color, _ in models],
        )
        axis.bar_label(bars, labels=[fmt.format(value) for value in values],
                       padding=3, fontsize=9, color=INK)
        axis.set_xticks([0, 1], [label for _, _, label in models], fontsize=9, color=INK)
        axis.set_ylim(0, max(values) * 1.25)
        axis.set_title(title, fontsize=10, color=INK, loc="left", pad=8)
        style(axis, grid="y")
    save(figure, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scores = json.loads(args.scores.read_text())
    strict_chart(args.output / "strict-by-task.svg", scores)
    cost_chart(args.output / "answer-cost.svg", scores)


if __name__ == "__main__":
    main()
