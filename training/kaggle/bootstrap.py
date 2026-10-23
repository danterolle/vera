import argparse
import hashlib
import json
import os
import subprocess
import sys
import venv
from pathlib import Path


def isolated_environment() -> dict[str, str]:
    environment = dict(os.environ)
    environment["PYTHONNOUSERSITE"] = "1"
    for name in ("PYTHONPATH", "PYTHONHOME"):
        environment.pop(name, None)
    return environment


def install_runtime(bundle: Path, work: Path) -> Path:
    bundle = bundle.resolve()
    work = work.resolve()
    manifest_path = bundle / "bundle.json"
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("format_version") != 2 or manifest.get("runtime_isolation") != "venv":
        raise ValueError("Upload the updated isolated-runtime bundle before installation")
    for relative, expected in manifest["files"].items():
        path = (bundle / relative).resolve()
        if not path.is_relative_to(bundle) or not path.is_file():
            raise ValueError(f"Invalid bundle file: {relative}")
        if hashlib.sha256(path.read_bytes()).hexdigest() != expected:
            raise ValueError(f"Bundle checksum mismatch: {relative}")
    requirements = bundle / "requirements-kaggle.txt"
    wheels = list((bundle / "wheels").glob("*.whl"))
    if len(wheels) != 1:
        raise ValueError("Expected exactly one VERA wheel")
    signature = hashlib.sha256(
        requirements.read_bytes() + wheels[0].read_bytes() + sys.version.encode()
    ).hexdigest()
    runtime = work / "runtime"
    python = runtime / "bin/python"
    if runtime.exists() and not (runtime / "pyvenv.cfg").is_file():
        raise RuntimeError("The runtime is not a virtual environment; choose a new work directory")
    if not runtime.exists():
        venv.EnvBuilder(with_pip=True, system_site_packages=False).create(runtime)
    marker = runtime / "installation.json"
    previous = json.loads(marker.read_text()) if marker.exists() else {}
    marker.unlink(missing_ok=True)
    configuration = (runtime / "pyvenv.cfg").read_text().lower().splitlines()
    if "include-system-site-packages = false" not in [line.strip() for line in configuration]:
        raise RuntimeError("The training runtime must not inherit global site packages")
    environment = isolated_environment()
    subprocess.run(
        [
            str(python), "-I", "-c",
            "import sys, site; assert sys.prefix != sys.base_prefix; "
            "assert not site.ENABLE_USER_SITE",
        ],
        env=environment, check=True,
    )
    pip = [str(python), "-I", "-m", "pip", "--isolated", "--require-virtualenv"]
    if previous.get("signature") != signature:
        subprocess.run(
            pip + ["install", "--quiet", "-r", str(requirements), str(wheels[0])],
            env=environment, check=True,
        )
    subprocess.run(pip + ["check"], env=environment, check=True)
    marker.write_text(json.dumps({
        "format_version": 2, "status": "ready", "signature": signature,
        "bundle_sha256": hashlib.sha256(manifest_path.read_bytes()).hexdigest(),
        "python": str(python),
    }, indent=2) + "\n", encoding="utf-8")
    print(f"Isolated training runtime ready: {python}")
    print("Continue with configuration; a notebook kernel restart is not required.")
    return python


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Install training packages outside Kaggle's kernel.",
    )
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--work", type=Path, required=True)
    args = parser.parse_args()
    install_runtime(args.bundle, args.work)


if __name__ == "__main__":
    main()
