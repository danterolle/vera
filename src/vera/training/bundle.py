import argparse
import json
import shutil
import subprocess
import tempfile
import zipfile
from pathlib import Path

from vera.training.audit import audit_dataset
from vera.training.build import build_dataset
from vera.training.data import file_hash


def prepare_bundle(
    root: Path, output: Path, *, seed: int = 3407, counts: dict[str, int] | None = None,
) -> Path:
    output = output.resolve()
    archive = output.with_suffix(".zip")
    if output.exists() or archive.exists():
        raise FileExistsError(f"Choose a new bundle output path: {output}")
    if shutil.which("uv") is None:
        raise RuntimeError("uv is required to build the installable VERA wheel")
    output.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="vera-sft-", dir=output.parent) as temporary:
        staging = Path(temporary) / output.name
        staging.mkdir()
        build_dataset(staging / "data", seed=seed, counts=counts)
        (staging / "quality-report.json").write_text(
            json.dumps(audit_dataset(staging / "data"), indent=2) + "\n",
            encoding="utf-8",
        )
        for source, name in (
            (root / "training/kaggle/requirements-lock.txt", "requirements-kaggle.txt"),
            (root / "training/kaggle/vera-qwen35.ipynb", "vera-qwen35.ipynb"),
            (root / "training/kaggle/bootstrap.py", "bootstrap.py"),
            (root / "training/kaggle/recover.py", "recover.py"),
            (root / "docs/fine-tuning.md", "INSTRUCTIONS.md"),
        ):
            shutil.copyfile(source, staging / name)
        subprocess.run(
            ["uv", "build", "--wheel", "--out-dir", str(staging / "wheels"), str(root)],
            check=True,
        )
        wheels = list((staging / "wheels").glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError("Expected exactly one VERA wheel")
        with zipfile.ZipFile(wheels[0]) as wheel:
            for name in wheel.namelist():
                path = Path(name)
                if (
                    any(part.startswith(".") for part in path.parts)
                    or path.suffix in {".db", ".kuzu", ".gguf", ".pyc"}
                ):
                    raise ValueError(f"Unexpected private/runtime file in wheel: {name}")
        files = sorted(path for path in staging.rglob("*") if path.is_file())
        manifest = {
            "format_version": 2,
            "workflow_version": 3,
            "runtime_isolation": "venv",
            "files": {str(path.relative_to(staging)): file_hash(path) for path in files},
            "notice": "Private synthetic bootstrap data; automated checks are not expert approval.",
            "training_location": "Kaggle only; bundle preparation never loads model weights.",
        }
        (staging / "bundle.json").write_text(json.dumps(manifest, indent=2) + "\n")
        staging.rename(output)
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as package:
        for path in sorted(output.rglob("*")):
            if path.is_file():
                package.write(path, str(path.relative_to(output)))
    return archive


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prepare a private Kaggle dataset; no training runs.",
    )
    parser.add_argument("--output", type=Path, default=Path(".vera/finetuning/vera-sft-v3"))
    parser.add_argument("--seed", type=int, default=3407)
    parser.add_argument("--train-size", type=int, default=2000)
    parser.add_argument("--validation-size", type=int, default=200)
    parser.add_argument("--test-size", type=int, default=300)
    args = parser.parse_args()
    root = Path.cwd()
    if not (root / "training/kaggle/vera-qwen35.ipynb").is_file():
        parser.error("Run this command from the VERA repository root")
    visible = root / args.output.with_suffix(".zip").name
    if visible.exists():
        parser.error(f"Choose a new output name; the visible upload already exists: {visible}")
    archive = prepare_bundle(root, args.output, seed=args.seed, counts={
        "train": args.train_size, "validation": args.validation_size, "test": args.test_size,
    })
    if archive != visible:
        with archive.open("rb") as source, visible.open("xb") as destination:
            shutil.copyfileobj(source, destination)
    print(f"Upload this archive as a private Kaggle Dataset: {visible}")
    print(f"Import this notebook into Kaggle: {args.output / 'vera-qwen35.ipynb'}")


if __name__ == "__main__":
    main()
