import argparse
import json
import math
import random
import time
from importlib.metadata import version
from pathlib import Path

from vera_finetuning.checkpoints import restore_checkpoint, save_checkpoint
from vera_finetuning.data import MODEL_ID, MODEL_REVISION, load_candidate, tokenize_splits
from vera_finetuning.model import build_model


def loss_for(model, example):
    import torch
    from torch.nn import functional as functional

    device = model.get_input_embeddings().weight.device
    tokens = torch.tensor([example["input_ids"]], device=device)
    count = tokens.shape[1] - example["prefix_length"]
    result = model(
        input_ids=tokens, attention_mask=torch.ones_like(tokens),
        logits_to_keep=count + 1, use_cache=False,
    )
    logits = result.logits[:, :-1]
    target = tokens[:, example["prefix_length"]:].to(logits.device)
    return functional.cross_entropy(logits.reshape(-1, logits.shape[-1]), target.reshape(-1))


def validation_loss(model, examples) -> float:
    import torch

    model.eval()
    with torch.no_grad():
        losses = [float(loss_for(model, example)) for example in examples]
    model.train()
    if not all(math.isfinite(value) for value in losses):
        raise RuntimeError("Validation produced a non-finite loss")
    return sum(losses) / len(losses)


def main() -> None:
    parser = argparse.ArgumentParser(description="Explicit, single-process FP32 LoRA experiment")
    parser.add_argument("--dataset", type=Path, required=True)
    parser.add_argument("--contract", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--resume", type=Path)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--pilot", action="store_true")
    mode.add_argument("--full", action="store_true")
    parser.add_argument("--acknowledge-candidate-data", action="store_true")
    args = parser.parse_args()
    if not args.acknowledge_candidate_data:
        parser.error("Review the synthetic dataset warnings and explicitly acknowledge them first")
    if args.resume and not (args.resume / "training-state.pt").is_file():
        parser.error("Resume requires a complete checkpoint, not only an adapter directory")
    if args.output.exists():
        parser.error("Choose a new output directory; existing experiments are never overwritten")
    import torch
    from transformers import AutoTokenizer

    packages = {
        name: version(name)
        for name in ("torch", "transformers", "peft", "accelerate", "torchao")
    }
    print(json.dumps({"packages": packages}), flush=True)
    contract = json.loads(args.contract.read_text())
    splits, warnings = load_candidate(args.dataset, contract)
    for warning in warnings:
        print(f"WARNING: {warning}", flush=True)
    tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, revision=MODEL_REVISION)
    encoded, tokens = tokenize_splits(tokenizer, splits, contract["max_length"])
    examples = encoded["train"]
    if args.pilot:
        longest = sorted(examples, key=lambda row: len(row["input_ids"]), reverse=True)
        largest_target = max(
            examples, key=lambda row: len(row["input_ids"]) - row["prefix_length"],
        )
        selected = {row["id"]: row for row in [longest[0], largest_target, *longest]}
        examples = list(selected.values())[:5]
    else:
        random.Random(3407).shuffle(examples)
    accumulation = 1 if args.pilot else 8
    args.output.mkdir(parents=True)
    progress = {
        "archive_sha256": contract["archive_sha256"],
        "system_prompt_sha256": contract["system_prompt_sha256"],
        "model_revision": MODEL_REVISION,
        "max_length": contract["max_length"],
        "mode": "pilot" if args.pilot else "full",
        "accumulation": accumulation, "steps": 0, "next_index": 0,
    }
    model = build_model(args.resume)
    trainable = [parameter for parameter in model.parameters() if parameter.requires_grad]
    optimizer = torch.optim.AdamW(trainable, lr=2e-5, weight_decay=0.01, foreach=False)
    if args.resume:
        progress = restore_checkpoint(optimizer, args.resume, progress)
    selected_validation = encoded["validation"][:4]
    before = validation_loss(model, selected_validation)
    for index in range(2):
        torch.cuda.reset_peak_memory_stats(index)
    started = time.monotonic()
    history = []
    for start in range(progress["next_index"], len(examples), accumulation):
        group = examples[start:start + accumulation]
        optimizer.zero_grad(set_to_none=True)
        losses = []
        for example in group:
            loss = loss_for(model, example)
            if not torch.isfinite(loss).item():
                raise RuntimeError(f"Non-finite training loss: {example['id']}")
            losses.append(float(loss.detach()))
            (loss / len(group)).backward()
        norm = torch.nn.utils.clip_grad_norm_(trainable, 1.0, foreach=False)
        if not torch.isfinite(norm).item():
            raise RuntimeError("Non-finite gradient norm; the experiment must not continue")
        optimizer.step()
        progress.update(steps=progress["steps"] + 1, next_index=start + len(group))
        record = {"step": progress["steps"], "loss": sum(losses) / len(losses)}
        history.append(record)
        print(json.dumps(record), flush=True)
        if progress["steps"] % 50 == 0:
            save_checkpoint(model, tokenizer, optimizer, args.output, progress)
    if progress["steps"] % 50:
        save_checkpoint(model, tokenizer, optimizer, args.output, progress)
    after = validation_loss(model, selected_validation)
    model.save_pretrained(args.output / "adapter", safe_serialization=True)
    tokenizer.save_pretrained(args.output / "adapter")
    report = {
        **progress, "model": MODEL_ID, "dtype": "float32", "parallelism": "model_parallel",
        "baseline_or_resume_validation_loss": before, "final_validation_loss": after,
        "validation_examples": [item["id"] for item in selected_validation],
        "training_seconds": round(time.monotonic() - started, 2),
        "peak_allocated_gib": [torch.cuda.max_memory_allocated(i) / 1024**3 for i in range(2)],
        "devices": {str(key): str(value) for key, value in model.hf_device_map.items()},
        "packages": packages,
        "tokens": tokens, "warnings": warnings, "loss_history": history,
        "test_used_for_selection": False, "deployment_authorized": False,
    }
    (args.output / "report.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2), flush=True)


if __name__ == "__main__":
    main()
