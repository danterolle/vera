import argparse
import inspect
import sys
from importlib.metadata import version
from pathlib import Path

from vera.training.runtime import language_model_class, save_json


def check_runtime() -> dict:
    if sys.prefix == sys.base_prefix:
        raise RuntimeError("Runtime validation must use the isolated training environment")
    model_class = language_model_class()
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is unavailable; check Kaggle's accelerator and driver")
    required = {
        "model_name", "max_seq_length", "dtype", "load_in_4bit", "load_in_16bit",
        "text_only", "use_exact_model_name",
    }
    if required - inspect.signature(model_class.from_pretrained).parameters.keys():
        raise RuntimeError("The installed Unsloth loader does not match the pinned recipe")
    from datasets import Dataset
    from peft import LoraConfig
    from trl import SFTConfig

    Dataset.from_list([{"input_ids": [1, 2], "labels": [-100, 2]}])
    LoraConfig(r=8, lora_alpha=16, target_modules="all-linear")
    SFTConfig(
        output_dir="/kaggle/working/vera-config-check", fp16=False, bf16=False,
        max_length=2048, dataset_kwargs={"skip_prepare_dataset": True}, report_to="none",
    )
    torch.ones(1).numpy()
    sample = torch.ones((16, 16), device="cuda")
    product = sample @ sample
    torch.cuda.synchronize()
    if not torch.isfinite(product).all().item():
        raise RuntimeError("The CUDA arithmetic probe produced non-finite values")
    properties = torch.cuda.get_device_properties(0)
    return {
        "passed": True, "python": sys.executable, "prefix": sys.prefix,
        "gpu": properties.name, "vram_gib": properties.total_memory / 1024**3,
        "cuda": torch.version.cuda, "compute_capability": list(torch.cuda.get_device_capability(0)),
        "packages": {
            package: version(package) for package in (
                "torch", "transformers", "trl", "peft", "datasets", "unsloth", "unsloth_zoo",
            )
        },
        "model_load_verified": False,
        "training_verified": False,
        "scope": "Imports, API compatibility and a small CUDA forward probe; no model weights.",
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Check isolated CUDA libraries without model weights.",
    )
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new runtime-check output path")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    try:
        report = check_runtime()
    except (ImportError, RuntimeError, OSError, TypeError, ValueError, AttributeError) as exc:
        save_json(args.output, {
            "passed": False, "error": str(exc), "error_type": type(exc).__name__,
        })
        raise
    save_json(args.output, report)
    print(f"Runtime libraries passed; model loading and training are not verified: {args.output}")


if __name__ == "__main__":
    main()
