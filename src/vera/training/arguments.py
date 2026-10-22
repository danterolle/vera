import argparse
import os
from pathlib import Path

MODEL = "Qwen/Qwen3.5-4B"
REVISION = "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"


def training_arguments(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a guarded Qwen3.5 VERA LoRA experiment.")
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--mode", choices=("smoke", "train"), default="smoke")
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--rank", type=int, default=8)
    parser.add_argument("--accumulation", type=int)
    parser.add_argument("--learning-rate", type=float, default=5e-5)
    parser.add_argument("--epochs", type=float, default=1.0)
    parser.add_argument("--steps", type=int, default=40)
    parser.add_argument("--smoke-report", type=Path)
    parser.add_argument("--resume", type=Path)
    args = parser.parse_args(argv)
    world = int(os.environ.get("WORLD_SIZE", "1"))
    if world not in {1, 2}:
        parser.error("This Kaggle recipe supports one or two GPUs")
    args.accumulation = 8 // world if args.accumulation is None else args.accumulation
    if not 256 <= args.max_length <= 8192 or not 1 <= args.rank <= 64:
        parser.error("Use a context of 256-8192 tokens and a LoRA rank of 1-64")
    if args.accumulation < 1 or args.steps < 1 or args.epochs <= 0:
        parser.error("Accumulation, steps and epochs must be positive")
    if not 0 < args.learning_rate <= 1e-3:
        parser.error("The learning rate must be positive and no greater than 1e-3")
    if args.mode == "train" and args.smoke_report is None:
        parser.error("Full training requires --smoke-report from a matching successful run")
    return args


def recipe(args: argparse.Namespace, manifest_hash: str) -> dict:
    return {
        "model": MODEL, "revision": REVISION, "manifest_sha256": manifest_hash,
        "max_length": args.max_length, "rank": args.rank, "alpha": 16,
        "learning_rate": args.learning_rate, "epochs": args.epochs,
        "world_size": int(os.environ.get("WORLD_SIZE", "1")),
        "accumulation": args.accumulation, "batch_per_device": 1,
        "mode": args.mode, "steps": args.steps if args.mode == "smoke" else None,
    }


def assert_matching_recipe(expected: dict, actual: dict, *, smoke: bool = False) -> None:
    ignored = {"mode", "steps", "epochs"} if smoke else set()
    if {key: value for key, value in expected.items() if key not in ignored} != {
        key: value for key, value in actual.items() if key not in ignored
    }:
        raise ValueError("The checkpoint or smoke report belongs to a different training recipe")
