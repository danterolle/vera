"""Render train and validation loss charts for the step-400 run."""

import argparse
import json
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt  # noqa: E402

matplotlib.rcParams["svg.hashsalt"] = "vera"

ADAPTER = "#1d4ed8"
FAINT = "#bfdbfe"
INK = "#1f2328"
MUTED = "#57606a"
GRID = "#e5e7eb"


def style(axis):
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d0d7de")
    axis.tick_params(colors=MUTED, labelsize=9)
    axis.yaxis.grid(True, color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)


def heading(figure, title, subtitle):
    figure.text(0.01, 0.97, title, fontsize=13, fontweight="bold", color=INK, va="top")
    figure.text(0.01, 0.91, subtitle, fontsize=9, color=MUTED, va="top")
    figure.subplots_adjust(top=0.80, left=0.11, right=0.98, bottom=0.15)


def save(figure, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path, format="svg", metadata={"Date": None}, bbox_inches="tight", pad_inches=0.08,
    )
    path.write_text("\n".join(line.rstrip() for line in path.read_text().splitlines()) + "\n")
    plt.close(figure)


def load_history(reports, extra):
    points = {}
    for path in reports:
        report = json.loads(path.read_text())
        for point in report["validation_history"]:
            points[point["step"]] = point["loss"]
    if extra:
        for point in json.loads(extra.read_text())["points"]:
            points[point["step"]] = point["loss"]
    return sorted(points.items())


def validation_chart(path, history):
    steps = [step for step, _ in history]
    losses = [loss for _, loss in history]
    figure, axis = plt.subplots(figsize=(8.6, 4.5))
    heading(
        figure,
        "Validation loss through step 400",
        "Fixed held-out examples: 16 every 20 steps to 160, then 24 every 60 steps",
    )
    axis.plot(steps, losses, color=ADAPTER, marker="o", linewidth=2.0, markersize=5)
    axis.set_yscale("log")
    annotations = {0: ((0, 9), "center"), 80: ((9, 9), "left"), 160: ((-7, -18), "right"),
                   240: ((0, 9), "center"), 400: ((0, 9), "center")}
    for step in annotations:
        offset, align = annotations[step]
        loss = dict(history)[step]
        axis.annotate(
            f"{loss:.4f}", (step, loss), textcoords="offset points", xytext=offset,
            ha=align, fontsize=9, color=INK,
        )
    axis.axvline(160, color=MUTED, linewidth=0.9, linestyle=":")
    axis.text(166, max(losses) * 0.72, "step-160 checkpoint", fontsize=8, color=MUTED)
    axis.set_xlim(-8, 412)
    axis.set_xticks([0, 80, 160, 240, 320, 400])
    axis.set_xlabel("Optimizer step", color=MUTED, fontsize=9)
    axis.set_ylabel("Validation loss (log scale)", color=MUTED, fontsize=9)
    style(axis)
    save(figure, path)


def train_chart(path, metrics_paths, window=20):
    rows = []
    for metrics_path in metrics_paths:
        rows.extend(
            json.loads(line) for line in metrics_path.read_text().splitlines() if line.strip()
        )
    train = sorted({row["step"]: row["loss"] for row in rows if row["event"] == "train"}.items())
    steps = [step for step, _ in train]
    losses = [loss for _, loss in train]
    means = [
        (step, sum(losses[max(0, index - window + 1):index + 1])
         / len(losses[max(0, index - window + 1):index + 1]))
        for index, step in enumerate(steps)
    ]
    figure, axis = plt.subplots(figsize=(8.6, 4.5))
    heading(
        figure,
        "Training loss over the first 160 updates",
        "Per-update loss and a 20-update moving average from the retained logs",
    )
    axis.plot(steps, losses, color=FAINT, linewidth=1.0)
    axis.plot([step for step, _ in means], [loss for _, loss in means],
              color=ADAPTER, linewidth=2.2)
    axis.set_yscale("log")
    annotations = {
        0: ((10, 0), "left", "center"),
        len(means) // 2: ((0, 10), "center", "bottom"),
        len(means) - 1: ((0, 12), "center", "bottom"),
    }
    for index, (offset, align, vertical) in annotations.items():
        step, loss = means[index]
        axis.annotate(f"{loss:.4f}", (step, loss), textcoords="offset points", xytext=offset,
                      ha=align, va=vertical, fontsize=9, color=INK)
    axis.set_xlim(0, 165)
    axis.set_xlabel("Optimizer step", color=MUTED, fontsize=9)
    axis.set_ylabel("Training loss (log scale)", color=MUTED, fontsize=9)
    style(axis)
    save(figure, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--extra-history", type=Path)
    parser.add_argument("--metrics", type=Path, action="append", default=[])
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    history = load_history(args.report, args.extra_history)
    validation_chart(args.output / "validation-loss.svg", history)
    if args.metrics:
        train_chart(args.output / "train-loss.svg", args.metrics)


if __name__ == "__main__":
    main()
