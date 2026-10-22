import argparse
from pathlib import Path

from vera.training.runtime import load_model, save_json


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Merge a verified VERA adapter or export its GGUF.",
    )
    parser.add_argument("--adapter", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--format", choices=("merged", "gguf"), default="merged")
    parser.add_argument("--quantization", choices=("q4_k_m", "q6_k"), default="q4_k_m")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("Use a new export directory")
    model, tokenizer, hardware = load_model(2048, adapter=args.adapter)
    if args.format == "merged":
        model.save_pretrained_merged(str(args.output), tokenizer, save_method="merged_16bit")
    else:
        model.save_pretrained_gguf(
            str(args.output), tokenizer, quantization_method=args.quantization,
        )
    save_json(args.output / "export.json", {
        "adapter": str(args.adapter), "format": args.format,
        "quantization": args.quantization if args.format == "gguf" else None,
        "hardware": hardware, "mtp_support": "not_verified",
    })


if __name__ == "__main__":
    main()
