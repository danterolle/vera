import argparse
import time
from pathlib import Path

from vera.training.arguments import MODEL, REVISION
from vera.training.data import encode_record, file_hash, read_records
from vera.training.records import fingerprint
from vera.training.runtime import language_model_class, load_model, save_json
from vera.training.scoring import score_answer


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Evaluate raw VERA answers without repair or fallback.",
    )
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--adapter", type=Path)
    parser.add_argument("--split", choices=("validation", "test"), default="validation")
    parser.add_argument("--limit", type=int, default=32)
    parser.add_argument("--max-length", type=int, default=2048)
    parser.add_argument("--max-new-tokens", type=int, default=1024)
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new evaluation output path to preserve earlier results")
    if not 1 <= args.max_new_tokens <= 2048:
        parser.error("max-new-tokens must be between 1 and 2048")
    records = read_records(args.data, args.split, args.limit)
    FastLanguageModel = language_model_class()
    import torch

    model, tokenizer, hardware = load_model(
        args.max_length + args.max_new_tokens, adapter=args.adapter,
    )
    FastLanguageModel.for_inference(model)
    results = []
    for record in records:
        encode_record(record, tokenizer, args.max_length)
        tokens = tokenizer.apply_chat_template(
            [message.model_dump() for message in record.messages[:-1]],
            tokenize=True, add_generation_prompt=True, enable_thinking=False,
            return_tensors="pt", return_dict=False,
        ).to(model.device)
        torch.cuda.synchronize()
        started = time.perf_counter()
        with torch.inference_mode():
            generated = model.generate(
                input_ids=tokens, attention_mask=torch.ones_like(tokens),
                max_new_tokens=args.max_new_tokens, do_sample=False,
                pad_token_id=tokenizer.pad_token_id, eos_token_id=tokenizer.eos_token_id,
            )[0, tokens.shape[-1]:]
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        text = tokenizer.decode(generated, skip_special_tokens=True).strip()
        truncated = (
            len(generated) >= args.max_new_tokens
            and int(generated[-1]) != tokenizer.eos_token_id
        )
        results.append({
            "id": record.id, "task": record.task, "seconds": elapsed,
            "generated_tokens": len(generated), "answer": text,
            **score_answer(text, record, truncated=truncated),
        })
        print(f"{len(results)}/{len(records)}: {record.task}: {results[-1]['passed']}", flush=True)
    metrics = ("json_valid", "contract_valid", "scope_match", "status_match",
               "factual_source_match", "passed", "truncated")
    args.output.parent.mkdir(parents=True, exist_ok=True)
    save_json(args.output, {
        "model": MODEL, "revision": REVISION,
        "adapter": str(args.adapter) if args.adapter else None,
        "manifest_sha256": file_hash(args.data / "manifest.json"),
        "split": args.split, "examples": len(results), "hardware": hardware,
        "generation": {
            "max_length": args.max_length, "max_new_tokens": args.max_new_tokens,
            "enable_thinking": False, "do_sample": False, "schema_enforced": False,
            "chat_template_sha256": fingerprint(tokenizer.chat_template),
        },
        "rates": {
            name: sum(bool(item[name]) for item in results) / len(results) for name in metrics
        },
        "average_seconds": sum(item["seconds"] for item in results) / len(results),
        "limitations": "Checks structured claims, not all summary semantics or HITL behavior.",
        "results": results,
    })


if __name__ == "__main__":
    main()
