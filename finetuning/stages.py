import argparse
import json
import re
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


def style(axis):
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d0d7de")
    axis.tick_params(colors=MUTED, labelsize=8)
    axis.yaxis.grid(True, color=GRID, linewidth=0.8)
    axis.set_axisbelow(True)


def heading(figure, title, subtitle):
    height = figure.get_figheight()
    figure.text(0.01, 0.98, title, fontsize=13, fontweight="bold", color=INK, va="top")
    figure.text(0.01, 0.98 - 0.30 / height, subtitle, fontsize=9, color=MUTED, va="top")
    figure.subplots_adjust(
        top=min(0.86, 0.98 - 0.42 / height), left=0.07, right=0.98, bottom=0.10,
    )


def save(figure, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(
        path, format="svg", metadata={"Date": None}, bbox_inches="tight", pad_inches=0.08,
    )
    plt.close(figure)


def adapter_steps(scores):
    steps = []
    for model in scores["models"]:
        match = re.fullmatch(r"adapter-(\d+)", model)
        if match:
            steps.append(int(match.group(1)))
    return sorted(steps)


def merged_history(paths):
    points = {}
    for path in paths:
        report = json.loads(path.read_text())
        for point in report["validation_history"]:
            points[int(point["step"])] = point["loss"]
    return sorted(points.items())


def loss_chart(path, reports, steps):
    points = merged_history(reports)
    xs = [step for step, _ in points]
    losses = [loss for _, loss in points]
    figure, axis = plt.subplots(figsize=(8.0, 4.2))
    heading(
        figure,
        "Validation loss across staged runs",
        "Same 16 fixed examples every 20 updates; points merged across resumed sessions",
    )
    axis.plot(xs, losses, color=ADAPTER, marker="o", linewidth=1.8, markersize=3.5)
    for step in steps:
        axis.axvline(step, color=BASE, linewidth=0.9, linestyle=":")
        axis.text(step, max(losses) * 1.02, f" {step}", color=MUTED, fontsize=8,
                  va="bottom")
    axis.set_xlim(min(xs) - 10, max(xs) + 10)
    axis.set_ylim(0, max(losses) * 1.12)
    axis.set_xlabel("Optimizer step", color=MUTED, fontsize=9)
    axis.set_ylabel("Validation loss", color=MUTED, fontsize=9)
    style(axis)
    save(figure, path)


def metric_value(summary, key):
    if key == "citation_clean_rate":
        value = summary.get("citation_failure_rate")
        return None if value is None else 1 - value
    return summary.get(key)


def behavior_chart(path, scores, steps):
    metrics = [
        ("JSON valid", "json_valid_rate", True),
        ("Schema valid", "schema_valid_rate", True),
        ("Scope correct", "scope_accuracy", True),
        ("Status recall", "mean_status_recall", True),
        ("Unavailable present", "unavailable_presence_rate", True),
        ("Citation clean", "citation_clean_rate", True),
        ("Exact quotes", "exact_quote_rate", True),
        ("Validation errors", "mean_validation_failures", False),
    ]
    figure, axes = plt.subplots(2, 4, figsize=(10.0, 7.0))
    heading(
        figure,
        "Answer-contract behavior across staged adapters",
        "33 validation examples, 3 per task, greedy decoding, base shown as a dashed line",
    )
    base = scores["models"]["base"]["overall"]
    models = [f"adapter-{step}" for step in steps]
    xs = steps
    for axis, (title, key, percent) in zip(axes.flat, metrics, strict=True):
        values = [
            metric_value(scores["models"][model]["overall"], key) for model in models
        ]
        base_value = metric_value(base, key)
        if base_value is not None:
            base_value = base_value * 100 if percent else base_value
            axis.axhline(base_value, color=BASE, linestyle="--", linewidth=1.2)
        plotted = [value * 100 if percent and value is not None else value for value in values]
        axis.plot(xs, plotted, color=ADAPTER, marker="o", linewidth=1.8, markersize=4)
        if percent:
            axis.set_ylim(0, 108)
            axis.set_yticks([0, 25, 50, 75, 100])
            axis.set_ylabel("Percent", color=MUTED, fontsize=8)
        else:
            axis.set_ylim(0, max([value for value in plotted if value is not None] + [0.6]) * 1.15)
            axis.set_ylabel("Mean per answer", color=MUTED, fontsize=8)
        last = plotted[-1]
        if last is not None:
            label = f"{last:.0f}" if percent else f"{last:.2f}"
            axis.annotate(
                label, (xs[-1], last), textcoords="offset points", xytext=(0, 8),
                ha="center", fontsize=8, color=INK,
            )
        axis.set_title(title, fontsize=9, color=INK, loc="left", pad=8)
        axis.set_xticks(xs)
        axis.set_xticklabels([str(step) for step in xs], fontsize=8)
        axis.set_xlabel("Adapter step", color=MUTED, fontsize=8)
        style(axis)
    figure.subplots_adjust(hspace=0.58, wspace=0.38)
    save(figure, path)


def task_chart(path, scores, steps):
    base = scores["models"]["base"]["by_task"]
    tasks = sorted(base)
    models = ["base", *[f"adapter-{step}" for step in steps]]
    columns = ["base", *[f"{step}" for step in steps]]
    values = [
        [scores["models"][model]["by_task"][task]["schema_valid_rate"] for model in models]
        for task in tasks
    ]
    figure, axis = plt.subplots(
        figsize=(max(6.5, 1.8 + 0.8 * len(models)), 1.4 + 0.38 * len(tasks)),
    )
    heading(
        figure,
        "Schema-valid answers by task across staged adapters",
        "Three sampled validation examples per task; cells show valid answers out of three",
    )
    image = axis.imshow(values, cmap="Blues", vmin=0, vmax=1, aspect="auto")
    for row in range(len(tasks)):
        for column in range(len(models)):
            value = values[row][column]
            axis.text(
                column, row, f"{round(value * 3)}/3", ha="center", va="center",
                fontsize=8, color="white" if value > 0.55 else INK,
            )
    axis.set_xticks(range(len(columns)), columns, fontsize=8, color=MUTED)
    axis.set_yticks(range(len(tasks)), [task.replace("_", " ") for task in tasks],
                    fontsize=8, color=INK)
    axis.set_xlabel("Checkpoint step", color=MUTED, fontsize=9)
    axis.tick_params(length=0)
    axis.axvline(0.5, color="white", linewidth=2)
    for spine in axis.spines.values():
        spine.set_visible(False)
    colorbar = figure.colorbar(image, ax=axis, fraction=0.03, pad=0.02)
    colorbar.set_label("Schema-valid rate", color=MUTED, fontsize=8)
    colorbar.ax.tick_params(colors=MUTED, labelsize=8)
    save(figure, path)


def main():
    parser = argparse.ArgumentParser(description="Chart staged fine-tuning results")
    parser.add_argument("--report", type=Path, action="append", required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    scores = json.loads(args.scores.read_text())
    steps = adapter_steps(scores)
    if not steps:
        raise ValueError("No adapter-<step> models found in the scores file")
    loss_chart(args.output / "validation-loss.svg", args.report, steps)
    behavior_chart(args.output / "behavior.svg", scores, steps)
    task_chart(args.output / "schema-by-task.svg", scores, steps)


if __name__ == "__main__":
    main()
