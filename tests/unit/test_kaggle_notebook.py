import hashlib
import json
import os
import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).parents[2]


@pytest.fixture
def notebook(tmp_path, monkeypatch):
    cells = json.loads((ROOT / "training/kaggle/vera-qwen35.ipynb").read_text())["cells"]
    sources = {cell["id"]: cell["source"] for cell in cells if cell["cell_type"] == "code"}
    bundle = tmp_path / "input"
    data = bundle / "data"
    data.mkdir(parents=True)
    (data / "manifest.json").write_text('{"purpose": "contract_bootstrap"}')
    (bundle / "quality-report.json").write_text('{"human_reviewed": false}')
    (bundle / "bundle.json").write_text("{}")
    work = tmp_path / "working"
    runtime = work / "runtime"
    (runtime / "bin").mkdir(parents=True)
    (runtime / "bin/python").touch()
    (runtime / "installation.json").write_text(json.dumps({
        "status": "ready",
        "bundle_sha256": hashlib.sha256((bundle / "bundle.json").read_bytes()).hexdigest(),
    }))
    calls = []
    monkeypatch.setattr(
        subprocess, "run",
        lambda command, **kwargs: calls.append((command, kwargs)) or SimpleNamespace(returncode=0),
    )
    namespace = {
        "BUNDLE": bundle, "DATA": data, "WORK": work,
        "hashlib": hashlib, "json": json, "os": os, "subprocess": subprocess, "Path": Path,
    }
    exec(compile(sources["configuration"], "configuration", "exec"), namespace)
    return sources, namespace, calls


def test_defaults_do_not_load_models_train_test_or_export(notebook):
    sources, namespace, calls = notebook
    for name in ("baseline", "smoke", "smoke-evaluation", "full-training"):
        exec(compile(sources[name], name, "exec"), namespace)
    assert calls == []


def test_runtime_and_preflight_use_isolated_python_and_clean_environment(notebook, monkeypatch):
    sources, namespace, calls = notebook
    monkeypatch.setenv("PYTHONPATH", "/global/python-packages")
    for name in ("runtime-check", "preflight"):
        exec(compile(sources[name], name, "exec"), namespace)
    assert len(calls) == 2
    for command, kwargs in calls:
        assert command[:3] == [str(namespace["RUNTIME_PYTHON"]), "-I", "-m"]
        assert "PYTHONPATH" not in kwargs["env"]
        assert kwargs["env"]["CUDA_VISIBLE_DEVICES"] == "0"


def test_default_flow_archives_diagnostics_without_requiring_an_adapter(notebook):
    sources, namespace, _ = notebook
    work = namespace["WORK"]
    (work / "runtime-check.json").write_text('{"passed": true}')
    (work / "preflight.json").write_text("{}")
    exec(compile(sources["download"], "download", "exec"), namespace)
    import zipfile

    with zipfile.ZipFile(work.parent / "vera-results-diagnostics.zip") as archive:
        assert "runtime-check.json" in archive.namelist()
        assert "preflight.json" in archive.namelist()
        assert "provenance/quality-report.json" in archive.namelist()
        assert not any("adapter" in name for name in archive.namelist())


def test_full_training_switch_is_not_an_approval_of_bootstrap_data(notebook):
    sources, namespace, calls = notebook
    namespace["RUN_FULL_TRAINING"] = True
    with pytest.raises(RuntimeError, match="contract-bootstrap"):
        exec(compile(sources["full-training"], "full-training", "exec"), namespace)
    assert calls == []


def test_diagnostics_can_be_saved_when_installation_failed_before_configuration(notebook):
    sources, namespace, _ = notebook
    for name in ("FULL", "SMOKE", "SMOKE_REPORT", "GPU_COUNT", "RUNTIME_PYTHON"):
        namespace.pop(name)
    exec(compile(sources["download"], "download", "exec"), namespace)
    assert (namespace["WORK"].parent / "vera-results-diagnostics.zip").is_file()
