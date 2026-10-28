import json
import random
import re
import time
from contextlib import nullcontext

from vera_finetuning.data import MODEL_ID, MODEL_REVISION, load_candidate
from vera_finetuning.model import load_base_model


def extract_json(text: str) -> dict | None:
    cleaned = text.strip()
    fenced = re.match(
        r"^```(?:json)?\s*(.*?)\s*```$", cleaned, re.DOTALL | re.IGNORECASE,
    )
    if fenced:
        cleaned = fenced.group(1)
    start = cleaned.find("{")
    if start < 0:
        return None
    try:
        payload, _ = json.JSONDecoder().raw_decode(cleaned[start:])
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def select_examples(splits: dict, split: str, per_task: int, seed: int) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for example in splits[split]:
        grouped.setdefault(example["task"], []).append(example)
    rng = random.Random(seed)
    selected = []
    for task in sorted(grouped):
        items = list(grouped[task])
        rng.shuffle(items)
        selected.extend(items[:per_task])
    return selected


def encode_prompt(tokenizer, example: dict) -> list[int]:
    return tokenizer.apply_chat_template(
        example["messages"][:-1], tokenize=True, return_dict=False,
        add_generation_prompt=True, enable_thinking=False,
    )


def generate(model, tokenizer, example: dict, max_new_tokens: int) -> tuple[str, int, int]:
    import torch

    input_ids = torch.tensor(
        [encode_prompt(tokenizer, example)],
        device=model.get_input_embeddings().weight.device,
    )
    attention_mask = torch.ones_like(input_ids)
    with torch.inference_mode():
        output = model.generate(
            input_ids=input_ids,
            attention_mask=attention_mask,
            max_new_tokens=max_new_tokens,
            do_sample=False,
            pad_token_id=tokenizer.eos_token_id,
            eos_token_id=tokenizer.eos_token_id,
        )
    generated = output[0, input_ids.shape[1]:]
    return (
        tokenizer.decode(generated, skip_special_tokens=True),
        int(input_ids.shape[1]),
        int(generated.shape[0]),
    )


def run(args) -> None:
    contract = json.loads(args.contract.read_text())
    splits, warnings = load_candidate(args.dataset, contract)
    examples = select_examples(splits, args.split, args.per_task, args.seed)
    if not examples:
        raise ValueError(f"No examples selected from the {args.split} split")
    for warning in warnings:
        print(f"WARNING: {warning}", flush=True)

    answers = args.output / "answers.jsonl"
    if answers.exists():
        raise FileExistsError(f"Refusing to overwrite {answers}")
    args.output.mkdir(parents=True, exist_ok=True)
    metadata = {
        "model": MODEL_ID,
        "revision": MODEL_REVISION,
        "adapter": str(args.adapter) if args.adapter else None,
        "split": args.split,
        "per_task": args.per_task,
        "seed": args.seed,
        "max_new_tokens": args.max_new_tokens,
        "examples": len(examples),
        "tasks": sorted({example["task"] for example in examples}),
        "warnings": warnings,
    }
    (args.output / "metadata.json").write_text(json.dumps(metadata, indent=2) + "\n")

    base = load_base_model()
    model = base
    if args.adapter:
        from peft import PeftModel

        model = PeftModel.from_pretrained(base, args.adapter, is_trainable=False)
    model.eval()
    model.config.use_cache = True
    disable_checkpointing = getattr(model, "gradient_checkpointing_disable", None)
    if disable_checkpointing is not None:
        disable_checkpointing()
    tokenizer = tokenizer_from(contract)

    labels = ["base", "adapter"] if args.adapter else ["base"]
    started = time.monotonic()
    with answers.open("w") as stream:
        for label in labels:
            context = (
                model.disable_adapter()
                if label == "base" and hasattr(model, "disable_adapter")
                else nullcontext()
            )
            with context:
                for index, example in enumerate(examples, start=1):
                    item_started = time.monotonic()
                    answer, input_tokens, output_tokens = generate(
                        model, tokenizer, example, args.max_new_tokens,
                    )
                    record = {
                        "model": label,
                        "id": example["id"],
                        "task": example["task"],
                        "answer": answer,
                        "input_tokens": input_tokens,
                        "output_tokens": output_tokens,
                        "seconds": round(time.monotonic() - item_started, 3),
                    }
                    stream.write(json.dumps(record) + "\n")
                    stream.flush()
                    print(json.dumps({
                        "model": label, "step": index, "total": len(examples),
                        "task": example["task"], "id": example["id"][:12],
                        "seconds": record["seconds"],
                    }), flush=True)
    print(json.dumps({
        "answers": str(answers),
        "generations": len(labels) * len(examples),
        "seconds": round(time.monotonic() - started, 2),
    }, indent=2), flush=True)


def tokenizer_from(contract: dict):
    from transformers import AutoTokenizer

    return AutoTokenizer.from_pretrained(
        contract["model"], revision=contract["model_revision"], trust_remote_code=False,
    )
