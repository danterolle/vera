"""Render held-out versus training-derived perturbed-probe charts."""

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


def style(axis):
    axis.spines[["top", "right"]].set_visible(False)
    axis.spines[["left", "bottom"]].set_color("#d0d7de")
    axis.tick_params(colors=MUTED, labelsize=9)
    axis.xaxis.grid(True, color=GRID, linewidth=0.8)
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


def metric(scores, model, key):
    overall = scores["models"][model]["overall"]
    return overall[key], overall["examples"]


def comparison_chart(path, training, held_out):
    groups = (
        ("Training-derived · rule pass", training, "runtime_normalized_rule_pass"),
        ("Training-derived · grounded", training, "grounded_behavior_pass"),
        ("Test-derived · rule pass", held_out, "runtime_normalized_rule_pass"),
        ("Test-derived · grounded", held_out, "grounded_behavior_pass"),
    )
    base_values, adapter_values, totals = [], [], []
    for _, source, key in groups:
        base, total = metric(source, "base", key)
        adapter, _ = metric(source, "adapter", key)
        base_values.append(base)
        adapter_values.append(adapter)
        totals.append(total)
    positions = list(range(len(groups)))
    height = 0.36
    figure, axis = plt.subplots(figsize=(8.6, 4.4))
    heading(
        figure,
        "Training-derived vs held-out probe",
        "40 perturbed cases each; the held-out set is built from the test split only",
    )
    figure.subplots_adjust(top=0.82, left=0.30, right=0.98, bottom=0.13)
    for offset, values, color, label in (
        (-height / 2, base_values, BASE, "Base"),
        (height / 2, adapter_values, ADAPTER, "Adapter 400"),
    ):
        bars = axis.barh([position + offset for position in positions], values, height,
                         color=color, label=label)
        axis.bar_label(bars, labels=[f"{value}/{total}" for value, total in zip(
            values, totals, strict=True)], padding=3, fontsize=8, color=INK)
    axis.set_yticks(positions, [label for label, _, _ in groups], fontsize=9, color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, 46)
    axis.set_xticks([0, 10, 20, 30, 40])
    axis.set_xlabel("Passing cases", color=MUTED, fontsize=9)
    style(axis)
    axis.legend(frameon=False, ncol=2, loc="lower center",
                bbox_to_anchor=(0.5, 1.01), fontsize=9)
    save(figure, path)


def family_chart(path, held_out):
    families = sorted(held_out["models"]["base"]["by_family"])
    positions = list(range(len(families)))
    height = 0.36
    figure, axis = plt.subplots(figsize=(8.6, 4.4))
    heading(
        figure,
        "Held-out probe by perturbation family",
        "Runtime-normalized rule pass on the test-derived 40-case set",
    )
    figure.subplots_adjust(top=0.82, left=0.20, right=0.98, bottom=0.13)
    for offset, model, color, label in (
        (-height / 2, "base", BASE, "Base"),
        (height / 2, "adapter", ADAPTER, "Adapter 400"),
    ):
        groups = held_out["models"][model]["by_family"]
        counts = [groups[family]["runtime_normalized_rule_pass"] for family in families]
        bars = axis.barh([position + offset for position in positions], counts, height,
                         color=color, label=label)
        axis.bar_label(bars, labels=[f"{value}/{groups[family]['examples']}"
                                     for value, family in zip(counts, families, strict=True)],
                       padding=3, fontsize=8, color=INK)
    axis.set_yticks(positions, [family.replace("_", " ") for family in families],
                    fontsize=9, color=INK)
    axis.invert_yaxis()
    axis.set_xlim(0, 9.4)
    axis.set_xticks(range(9))
    axis.set_xlabel("Passing cases", color=MUTED, fontsize=9)
    style(axis)
    axis.legend(frameon=False, ncol=2, loc="lower center",
                bbox_to_anchor=(0.5, 1.01), fontsize=9)
    save(figure, path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--training", type=Path, required=True)
    parser.add_argument("--held-out", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    training = json.loads(args.training.read_text())
    held_out = json.loads(args.held_out.read_text())
    comparison_chart(args.output / "heldout-comparison.svg", training, held_out)
    family_chart(args.output / "heldout-family.svg", held_out)


if __name__ == "__main__":
    main()
