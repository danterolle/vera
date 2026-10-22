import json
import os
import subprocess
import sys
from pathlib import Path

from vera.training.arguments import MODEL, REVISION


def language_model_class():
    from unsloth import FastLanguageModel

    return FastLanguageModel


def load_model(max_length: int, rank: int | None = None, *, adapter: Path | None = None):
    FastLanguageModel = language_model_class()
    import torch

    if not torch.cuda.is_available():
        raise RuntimeError("CUDA is required. Enable a Kaggle GPU accelerator.")
    local_rank = int(os.environ.get("LOCAL_RANK", "0"))
    torch.cuda.set_device(local_rank)
    native_bf16 = torch.cuda.get_device_capability(local_rank)[0] >= 8
    if adapter is not None:
        configuration = json.loads((adapter / "recipe.json").read_text())
        peft = json.loads((adapter / "adapter_config.json").read_text())
        if configuration["model"] != MODEL or configuration["revision"] != REVISION:
            raise ValueError("The adapter was trained against a different base model revision")
        if peft.get("revision") != REVISION or peft["base_model_name_or_path"] != MODEL:
            raise ValueError("The adapter does not pin the expected base model revision")
    model, tokenizer = FastLanguageModel.from_pretrained(
        model_name=str(adapter) if adapter else MODEL,
        revision=None if adapter else REVISION, max_seq_length=max_length,
        dtype=torch.bfloat16 if native_bf16 else torch.float16,
        load_in_4bit=False, load_in_16bit=True, full_finetuning=False,
        use_exact_model_name=True,
        text_only=True, device_map={"": local_rank},
        use_gradient_checkpointing="unsloth",
    )
    forced_float32 = bool(getattr(model, "_unsloth_forced_float32", False))
    if rank is not None and not native_bf16 and not forced_float32:
        raise RuntimeError(
            "The installed loader did not enable Qwen3.5 float32 safeguards on this GPU. "
            "Do not force FP16; restore the bundled Unsloth revisions."
        )
    if rank is not None:
        model = FastLanguageModel.get_peft_model(
            model, r=rank, lora_alpha=16, lora_dropout=0,
            target_modules="all-linear", bias="none",
            use_gradient_checkpointing="unsloth", random_state=3407,
        )
        trainable = [name for name, value in model.named_parameters() if value.requires_grad]
        if not trainable or any("lora_" not in name for name in trainable):
            raise RuntimeError("Only LoRA adapter parameters may be trainable")
    else:
        model.requires_grad_(False)
    tokenizer.padding_side = "right"
    return model, tokenizer, {
        "native_bf16": native_bf16, "forced_float32": forced_float32,
        "gpu": torch.cuda.get_device_name(local_rank),
        "vram_gib": torch.cuda.get_device_properties(local_rank).total_memory / 1024**3,
        "torch": torch.__version__, "cuda": torch.version.cuda,
        "trainable_parameters": sum(p.numel() for p in model.parameters() if p.requires_grad),
    }


def save_json(path: Path, value: dict) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def save_environment(directory: Path) -> None:
    completed = subprocess.run(
        [sys.executable, "-m", "pip", "freeze"], check=True, capture_output=True, text=True,
    )
    (directory / "environment.txt").write_text(completed.stdout, encoding="utf-8")
