"""Run evaluation-only base/adapter inference in a private Kaggle kernel."""

import os
import subprocess
import sys
import zipfile
from pathlib import Path

INPUT = Path("/kaggle/input")
WORK = Path("/kaggle/working/vera-eval-v2-110")
TEMP = Path("/kaggle/temp/vera-eval-v2-110")


def unique_input(name: str) -> Path:
    matches = [path for path in INPUT.rglob(name) if path.is_file()]
    if not matches and name.endswith(".zip"):
        stem = Path(name).stem
        matches = [path for path in INPUT.rglob(stem) if path.is_dir()]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one Kaggle input named {name}, found {len(matches)}")
    return matches[0]


def run(command: list[str], env: dict[str, str], timeout: int) -> None:
    subprocess.run(command, check=True, env=env, timeout=timeout)


def main() -> None:
    if WORK.exists() or TEMP.exists():
        raise FileExistsError("Refusing to overwrite an existing Kaggle evaluation run")
    WORK.mkdir(parents=True)
    TEMP.mkdir(parents=True)
    dataset = unique_input("vera-domain-v2-candidate.zip")
    selection = unique_input("selection.json")
    contract = unique_input("runtime-contract.json")
    code_archive = unique_input("vera-evaluation-only-code.zip")
    adapter_config = unique_input("adapter_config.json")
    adapter = adapter_config.parent
    if not (adapter / "adapter_model.safetensors").is_file():
        raise FileNotFoundError("The step-400 adapter weights are missing")

    if code_archive.is_dir():
        code = code_archive
    else:
        code = TEMP / "code"
        code.mkdir()
        with zipfile.ZipFile(code_archive) as archive:
            members = archive.infolist()
            if any(
                Path(member.filename).is_absolute() or ".." in Path(member.filename).parts
                for member in members
            ):
                raise ValueError("Evaluation code archive contains an unsafe path")
            archive.extractall(code)

    env = os.environ.copy()
    env.update({
        "HF_HOME": str(TEMP / "huggingface"),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONPATH": str(code),
        "TOKENIZERS_PARALLELISM": "false",
    })
    venv = TEMP / "venv"
    run([
        sys.executable, "-m", "venv", "--without-pip", "--system-site-packages", str(venv),
    ], env, 120)
    python = str(venv / "bin" / "python")
    run([
        sys.executable, "-m", "pip", "--python", python, "install",
        "--disable-pip-version-check", "-r", str(code / "requirements-evaluation-kaggle.txt"),
    ], env, 7200)
    run(["nvidia-smi"], env, 30)
    run([
        python, "-m", "vera_finetuning.preflight",
        "--dataset", str(dataset), "--contract", str(contract),
        "--output", str(WORK / "preflight.json"),
    ], env, 3600)
    run([
        python, str(code / "evaluate.py"),
        "--dataset", str(dataset), "--contract", str(contract),
        "--output", str(WORK / "results"), "--adapter", str(adapter),
        "--split", "validation", "--per-task", "10",
        "--selection", str(selection), "--max-new-tokens", "768",
        "--seed", "20261102",
    ], env, 14400)


if __name__ == "__main__":
    main()
