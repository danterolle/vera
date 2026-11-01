"""Run evaluation-only base/adapter inference in a private Kaggle kernel."""

import json
import os
import subprocess
import sys
import zipfile
from pathlib import Path

INPUT = Path("/kaggle/input")
WORK_ROOT = Path("/kaggle/working")
TEMP_ROOT = Path("/kaggle/temp")


def unique_file(name: str) -> Path:
    matches = [path for path in INPUT.rglob(name) if path.is_file()]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one Kaggle input named {name}, found {len(matches)}")
    return matches[0]


def has_zip_member(path: Path, name: str) -> bool:
    try:
        with zipfile.ZipFile(path) as archive:
            return name in archive.namelist()
    except zipfile.BadZipFile:
        return False


def unique_candidate() -> Path:
    matches = [path.parent for path in INPUT.rglob("package.json") if path.is_file()]
    if not matches:
        matches = [
            path for path in INPUT.rglob("*.zip") if has_zip_member(path, "package.json")
        ]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one candidate package, found {len(matches)}")
    return matches[0]


def unique_code() -> Path:
    directories = [
        path.parent for path in INPUT.rglob("evaluate.py")
        if path.is_file() and (path.parent / "requirements-evaluation-kaggle.txt").is_file()
    ]
    matches = directories
    if not matches:
        matches = [
            path for path in INPUT.rglob("*.zip")
            if has_zip_member(path, "evaluate.py")
            and has_zip_member(path, "requirements-evaluation-kaggle.txt")
        ]
    if len(matches) != 1:
        raise FileNotFoundError(f"Expected one evaluation code bundle, found {len(matches)}")
    return matches[0]


def run(command: list[str], env: dict[str, str], timeout: int) -> None:
    subprocess.run(command, check=True, env=env, timeout=timeout)


def materialize_code(source: Path, temp: Path) -> Path:
    if source.is_dir():
        return source
    code = temp / "code"
    code.mkdir()
    with zipfile.ZipFile(source) as archive:
        members = archive.infolist()
        if any(
            Path(member.filename).is_absolute() or ".." in Path(member.filename).parts
            for member in members
        ):
            raise ValueError("Evaluation code archive contains an unsafe path")
        archive.extractall(code)
    return code


def main() -> None:
    selection_path = unique_file("selection.json")
    selection = json.loads(selection_path.read_text())
    run_name = (
        f"validation-{selection['split']}-{len(selection['selected_ids'])}"
        f"-seed-{selection['seed']}"
    )
    work = WORK_ROOT / f"vera-{run_name}"
    temp = TEMP_ROOT / f"vera-{run_name}"
    if work.exists() or temp.exists():
        raise FileExistsError("Refusing to overwrite an existing Kaggle evaluation run")
    work.mkdir(parents=True)
    temp.mkdir(parents=True)
    dataset = unique_candidate()
    contract = unique_file("runtime-contract.json")
    code = materialize_code(unique_code(), temp)
    adapter_config = unique_file("adapter_config.json")
    adapter = adapter_config.parent
    if not (adapter / "adapter_model.safetensors").is_file():
        raise FileNotFoundError("The adapter weights are missing")

    env = os.environ.copy()
    env.update({
        "HF_HOME": str(temp / "huggingface"),
        "HF_HUB_DISABLE_TELEMETRY": "1",
        "PYTHONPATH": str(code),
        "TOKENIZERS_PARALLELISM": "false",
    })
    venv = temp / "venv"
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
        "--output", str(work / "preflight.json"),
    ], env, 3600)
    run([
        python, str(code / "evaluate.py"),
        "--dataset", str(dataset), "--contract", str(contract),
        "--output", str(work / "results"), "--adapter", str(adapter),
        "--split", selection["split"], "--per-task", str(selection["per_task"]),
        "--selection", str(selection_path), "--max-new-tokens", str(selection["max_new_tokens"]),
        "--seed", str(selection["seed"]),
    ], env, 14400)


if __name__ == "__main__":
    main()
