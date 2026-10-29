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


def style(axis):
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d0d7de")
    axis.tick_params(colors=MUTED, labelsize=9)
    axis.yaxis.grid(True, color="#e5e7eb", linewidth=0.8)
    axis.set_axisbelow(True)


def heading(figure, title, subtitle):
    figure.text(0.01, 0.97, title, fontsize=13, fontweight="bold", color=INK, va="top")
    figure.text(0.01, 0.90, subtitle, fontsize=9, color=MUTED, va="top")
    figure.subplots_adjust(top=0.80, left=0.09, right=0.98, bottom=0.14)


def save(figure, path):
    path.parent.mkdir(parents=True, exist_ok=True)
    figure.savefig(path, format="svg", metadata={"Date": None}, bbox_inches="tight",
                   pad_inches=0.08)
    plt.close(figure)


def loss_chart(path, report):
    points = report["validation_history"]
    steps = [point["step"] for point in points]
    losses = [point["loss"] for point in points]
    figure, axis = plt.subplots(figsize=(8.0, 4.2))
    heading(
        figure,
        "Validation loss during the bounded preview",
        "80 optimizer updates; 16 fixed validation examples every 20 steps",
    )
    axis.plot(steps, losses, color=ADAPTER, marker="o", linewidth=2.0, markersize=5)
    for step, loss in zip(steps, losses, strict=True):
        axis.annotate(
            f"{loss:.3f}", (step, loss), textcoords="offset points", xytext=(0, 9),
            ha="center", fontsize=9, color=INK,
        )
    axis.set_ylim(0, max(losses) * 1.22)
    axis.set_xlim(min(steps) - 4, max(steps) + 4)
    axis.set_xlabel("Optimizer step", color=MUTED, fontsize=9)
    axis.set_ylabel("Validation loss", color=MUTED, fontsize=9)
    style(axis)
    save(figure, path)


def behavior_chart(path, base, adapter):
    metrics = [
        ("JSON valid", "json_valid_rate"),
        ("Schema valid", "schema_valid_rate"),
        ("Scope", "scope_accuracy"),
        ("Status recall", "mean_status_recall"),
        ("Unavailable", "unavailable_presence_rate"),
        ("Exact quotes", "exact_quote_rate"),
    ]
    positions = list(range(len(metrics)))
    base_values = [base[key] * 100 for _, key in metrics]
    adapter_values = [adapter[key] * 100 for _, key in metrics]
    figure, axis = plt.subplots(figsize=(8.0, 4.2))
    heading(
        figure,
        "Answer-contract behavior: base vs adapter",
        "33 validation examples, 3 per task, greedy decoding, identical prompts",
    )
    width = 0.36
    for offset, values, color, label in (
        (-width / 2, base_values, BASE, "Base"),
        (width / 2, adapter_values, ADAPTER, "Adapter"),
    ):
        bars = axis.bar(
            [position + offset for position in positions], values, width,
            color=color, label=label,
        )
        axis.bar_label(bars, fmt="%.0f", padding=3, fontsize=9, color=INK)
    axis.set_xticks(positions, [label for label, _ in metrics], fontsize=9, color=MUTED)
    axis.set_ylim(0, 108)
    axis.set_ylabel("Percent of sampled examples", color=MUTED, fontsize=9)
    axis.legend(frameon=False, ncol=2, loc="lower center",
                bbox_to_anchor=(0.5, 1.01), fontsize=9)
    style(axis)
    save(figure, path)


def task_chart(path, tasks, base_counts, adapter_counts):
    positions = list(range(len(tasks)))
    figure, axis = plt.subplots(figsize=(8.0, 1.2 + 0.36 * len(tasks)))
    heading(
        figure,
        "Schema-valid answers by task",
        "Number of valid answers out of three sampled examples per task",
    )
    height = 0.36
    axis.barh([position - height / 2 for position in positions], base_counts, height,
              color=BASE, label="Base")
    axis.barh([position + height / 2 for position in positions], adapter_counts, height,
              color=ADAPTER, label="Adapter")
    for position, value in zip(positions, base_counts, strict=True):
        axis.text(value + 0.05, position - height / 2, f"{value}/3", va="center",
                  fontsize=9, color=INK)
    for position, value in zip(positions, adapter_counts, strict=True):
        axis.text(value + 0.05, position + height / 2, f"{value}/3", va="center",
                  fontsize=9, color=INK)
    axis.set_yticks(positions, [task.replace("_", " ") for task in tasks], fontsize=9,
                    color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, 3.4)
    axis.set_xticks(range(4))
    axis.set_xlabel("Valid answers", color=MUTED, fontsize=9)
    axis.xaxis.grid(True, color="#e5e7eb", linewidth=0.8)
    axis.yaxis.grid(False)
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d0d7de")
    axis.tick_params(colors=MUTED, labelsize=9)
    axis.set_axisbelow(True)
    axis.legend(frameon=False, ncol=2, loc="lower center",
                bbox_to_anchor=(0.5, 1.01), fontsize=9)
    save(figure, path)


def main():
    parser = argparse.ArgumentParser(description="Render fine-tuning preview charts as SVG")
    parser.add_argument("--report", type=Path, required=True)
    parser.add_argument("--scores", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    report = json.loads(args.report.read_text())
    scores = json.loads(args.scores.read_text())
    base = scores["models"]["base"]["overall"]
    adapter = scores["models"]["adapter"]["overall"]
    loss_chart(args.output / "validation-loss.svg", report)
    behavior_chart(args.output / "behavior.svg", base, adapter)
    tasks = sorted(scores["models"]["base"]["by_task"])

    def valid(model):
        by_task = scores["models"][model]["by_task"]
        return [round(by_task[task]["schema_valid_rate"] * 3) for task in tasks]

    task_chart(args.output / "schema-by-task.svg", tasks, valid("base"), valid("adapter"))


if __name__ == "__main__":
    main()
