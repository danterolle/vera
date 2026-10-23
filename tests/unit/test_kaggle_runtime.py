import hashlib
import importlib.util
import json
import subprocess
import venv
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[2]


@pytest.fixture
def bootstrap(tmp_path, monkeypatch):
    path = ROOT / "training/kaggle/bootstrap.py"
    spec = importlib.util.spec_from_file_location("kaggle_bootstrap", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    builder = venv.EnvBuilder
    monkeypatch.setattr(
        module.venv, "EnvBuilder",
        lambda **kwargs: builder(with_pip=False, system_site_packages=False),
    )
    bundle = tmp_path / "bundle"
    (bundle / "wheels").mkdir(parents=True)
    (bundle / "wheels/vera.whl").write_bytes(b"test wheel")
    (bundle / "requirements-kaggle.txt").write_text("")
    files = ("requirements-kaggle.txt", "wheels/vera.whl")
    (bundle / "bundle.json").write_text(json.dumps({
        "format_version": 2, "runtime_isolation": "venv",
        "files": {
            name: hashlib.sha256((bundle / name).read_bytes()).hexdigest() for name in files
        },
    }))
    original_run = subprocess.run
    calls = []
    fail_check = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        if "pip" in command:
            if command[-1] == "check" and fail_check:
                raise subprocess.CalledProcessError(1, command)
            return SimpleNamespace(returncode=0)
        return original_run(command, **kwargs)

    monkeypatch.setattr(module.subprocess, "run", run)
    return module, bundle, tmp_path / "work", calls, fail_check


def test_bootstrap_uses_only_isolated_python_and_checks_dependencies(bootstrap, monkeypatch):
    module, bundle, work, calls, _ = bootstrap
    monkeypatch.setenv("PYTHONPATH", "/untrusted/global/site-packages")
    python = module.install_runtime(bundle, work)
    pip_calls = [(command, kwargs) for command, kwargs in calls if "pip" in command]
    assert all(command[0] == str(python) for command, _ in pip_calls)
    assert all("--require-virtualenv" in command for command, _ in pip_calls)
    assert all("PYTHONPATH" not in kwargs["env"] for _, kwargs in calls)
    assert [command[-1] for command, _ in pip_calls][-1] == "check"
    marker = work / "runtime/installation.json"
    assert json.loads(marker.read_text())["status"] == "ready"
    module.install_runtime(bundle, work)
    assert sum("install" in command for command, _ in calls) == 1
    assert sum(command[-1] == "check" for command, _ in calls) == 2


def test_failed_dependency_check_invalidates_a_previous_ready_marker(bootstrap):
    module, bundle, work, _, fail_check = bootstrap
    module.install_runtime(bundle, work)
    fail_check.append(True)
    with pytest.raises(subprocess.CalledProcessError):
        module.install_runtime(bundle, work)
    assert not (work / "runtime/installation.json").exists()


def test_bootstrap_rejects_inherited_global_packages(bootstrap):
    module, bundle, work, _, _ = bootstrap
    module.install_runtime(bundle, work)
    configuration = work / "runtime/pyvenv.cfg"
    configuration.write_text(configuration.read_text().replace(
        "include-system-site-packages = false", "include-system-site-packages = true",
    ))
    with pytest.raises(RuntimeError, match="global site packages"):
        module.install_runtime(bundle, work)
    assert not (work / "runtime/installation.json").exists()


def test_recovery_cell_works_with_the_already_attached_dataset(bootstrap):
    _, bundle, work, calls, _ = bootstrap
    work.mkdir()
    source = (ROOT / "training/kaggle/recover.py").read_text()
    namespace = {"BUNDLE": bundle, "WORK": work}
    exec(compile(source, "kaggle-recovery-cell", "exec"), namespace)
    assert namespace["DATA"] == bundle / "data"
    assert namespace["RUN_FULL_TRAINING"] is False
    assert namespace["GPU_COUNT"] == 1
    before = len(calls)
    namespace["run"]("pip", ["check"])
    command, kwargs = calls[before]
    assert command[0] == str(work / "runtime/bin/python")
    assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "0"


def test_real_virtual_environment_uses_its_own_pip(tmp_path):
    runtime = tmp_path / "real-runtime"
    venv.EnvBuilder(with_pip=True, system_site_packages=False).create(runtime)
    python = runtime / "bin/python"
    result = subprocess.run(
        [str(python), "-I", "-m", "pip", "--isolated", "--require-virtualenv", "check"],
        check=True, capture_output=True, text=True,
    )
    assert "No broken requirements found" in result.stdout
    result = subprocess.run(
        [
            str(python), "-I", "-c",
            "import json, sys, site; print(json.dumps({"
            "'prefix':sys.prefix,'base':sys.base_prefix,'user':site.ENABLE_USER_SITE}))",
        ],
        check=True, capture_output=True, text=True,
    )
    information = json.loads(result.stdout)
    assert information["prefix"] == str(runtime)
    assert information["prefix"] != information["base"]
    assert information["user"] is False
