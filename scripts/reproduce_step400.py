"""Download pinned public artifacts, run llama-server, and reproduce the VERA A/B check."""

import argparse
import hashlib
import json
import shutil
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

BASE_REPO = "unsloth/Qwen3.5-4B-MTP-GGUF"
BASE_REVISION = "86835bf9949e4d14d6860f7910b1340ad4f271a9"
BASE_FILE = "Qwen3.5-4B-Q6_K.gguf"
BASE_SHA256 = "d8fe325a6184ac489529bb2286e879865d02acdd710ac0a54a0afa3e66051b87"
ADAPTER_REPO = "danterolle/vera-qwen35-4b-step400-adapter"
ADAPTER_REVISION = "75c7977203835cfe39999dcae982a040b7bf5c5b"
ADAPTER_FILE = "vera-step400-lora-f16.gguf"
ADAPTER_SHA256 = "0db9ad4836e790b09580651b7b0a0f574b4d6ab950d8089f3cc31e84e28c66e2"
LLAMA_CPP_COMMIT = "8642541b2"
MODEL_ID = "vera-qwen3.5-4b-step400"


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_artifact(
    existing: Path, cache: Path, repo: str, revision: str, filename: str, checksum: str
) -> Path:
    for candidate in (existing, cache / filename):
        if candidate.is_file() and sha256(candidate) == checksum:
            return candidate
    target = cache / filename
    if target.exists():
        raise ValueError(f"Cached artifact has the wrong checksum: {target}")
    cache.mkdir(parents=True, exist_ok=True)
    from huggingface_hub import hf_hub_download

    downloaded = Path(hf_hub_download(
        repo_id=repo, filename=filename, revision=revision,
        local_dir=str(cache), token=False,
    ))
    if sha256(downloaded) != checksum:
        raise ValueError(f"Downloaded artifact checksum mismatch: {filename}")
    return downloaded


def require_llama_server(command: str) -> str:
    executable = shutil.which(command)
    if executable is None and Path(command).is_file():
        executable = str(Path(command).resolve())
    if executable is None:
        raise FileNotFoundError(
            "Install llama-server built from llama.cpp commit "
            f"{LLAMA_CPP_COMMIT} and make it available in PATH."
        )
    result = subprocess.run(
        [executable, "--version"], check=True, capture_output=True, text=True,
    )
    version = result.stdout + result.stderr
    if LLAMA_CPP_COMMIT not in version:
        raise RuntimeError(f"llama-server must use llama.cpp commit {LLAMA_CPP_COMMIT}")
    return executable


def wait_for_server(process: subprocess.Popen, url: str, log_path: Path, timeout: int) -> None:
    deadline = time.monotonic() + timeout
    with httpx.Client(base_url=url, timeout=2) as client:
        while time.monotonic() < deadline:
            if process.poll() is not None:
                detail = "\n".join(log_path.read_text(errors="replace").splitlines()[-30:])
                raise RuntimeError(f"llama-server exited during startup:\n{detail}")
            try:
                models = client.get("/v1/models")
                adapters = client.get("/lora-adapters")
                models.raise_for_status()
                adapters.raise_for_status()
                model_ids = {item["id"] for item in models.json().get("data", [])}
                loaded = any(
                    Path(item.get("path", "")).name == ADAPTER_FILE
                    and float(item.get("scale", 0)) == 1
                    for item in adapters.json()
                )
                if MODEL_ID in model_ids and loaded:
                    return
            except httpx.HTTPError:
                time.sleep(1)
        raise TimeoutError(f"llama-server did not become ready at {url}")


def run(args: argparse.Namespace) -> dict:
    root = Path(__file__).resolve().parents[1]
    server_binary = require_llama_server(args.llama_server)
    with socket.socket() as probe:
        if probe.connect_ex(("127.0.0.1", args.port)) == 0:
            raise OSError(f"Port {args.port} is already in use; choose another --port")

    artifact_dir = root / ".vera/reproduce-step400"
    base = ensure_artifact(
        root / ".vera/models/qwen3.5-4b-mtp" / BASE_FILE,
        artifact_dir / "base", BASE_REPO, BASE_REVISION, BASE_FILE, BASE_SHA256,
    )
    adapter = ensure_artifact(
        root / ".vera/finetuning/adapter-step400" / ADAPTER_FILE,
        artifact_dir / "adapter", ADAPTER_REPO, ADAPTER_REVISION, ADAPTER_FILE,
        ADAPTER_SHA256,
    )
    url = f"http://127.0.0.1:{args.port}"
    command = [
        server_binary, "-m", str(base), "--lora", str(adapter),
        "-ngl", str(args.gpu_layers), "-fa", "on", "--ctx-size", "8192",
        "--parallel", "1", "--reasoning", "off", "--reasoning-budget", "0",
        "--host", "127.0.0.1", "--port", str(args.port), "--alias", MODEL_ID,
    ]
    with tempfile.TemporaryDirectory(prefix="vera-step400-server-") as directory:
        log_path = Path(directory) / "server.log"
        with log_path.open("w", encoding="utf-8") as log:
            process = subprocess.Popen(command, stdout=log, stderr=subprocess.STDOUT)
            try:
                wait_for_server(process, url, log_path, args.startup_timeout)
                sys.path.insert(0, str(root / "finetuning"))
                from check_local_adapter import run as run_ab_check

                report = run_ab_check(argparse.Namespace(
                    server_url=url, model=MODEL_ID, adapter_id=None,
                    timeout=args.request_timeout, output=None,
                ))
            finally:
                if process.poll() is None:
                    process.terminate()
                    try:
                        process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
    report["artifacts"] = {
        "base_repo": BASE_REPO,
        "base_revision": BASE_REVISION,
        "base_sha256": BASE_SHA256,
        "adapter_repo": ADAPTER_REPO,
        "adapter_revision": ADAPTER_REVISION,
        "adapter_file": ADAPTER_FILE,
        "adapter_sha256": ADAPTER_SHA256,
        "llama_cpp_commit": LLAMA_CPP_COMMIT,
    }
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--llama-server", default="llama-server")
    parser.add_argument("--port", type=int, default=1235)
    parser.add_argument("--gpu-layers", type=int, default=99)
    parser.add_argument("--startup-timeout", type=int, default=180)
    parser.add_argument("--request-timeout", type=float, default=180)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    if not 1 <= args.port <= 65535 or args.gpu_layers < 0:
        parser.error("--port must be 1..65535 and --gpu-layers cannot be negative")
    if args.startup_timeout < 1 or args.request_timeout <= 0:
        parser.error("timeouts must be positive")
    if args.output and args.output.exists():
        parser.error("Choose a new report path; existing files are never overwritten")
    report = run(args)
    rendered = json.dumps(report, ensure_ascii=False, indent=2) + "\n"
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(rendered, encoding="utf-8")
    print(rendered, end="")


if __name__ == "__main__":
    main()
