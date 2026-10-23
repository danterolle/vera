import ast
import json
import zipfile
from pathlib import Path

import nbformat
import pytest

from vera.training.bundle import main, prepare_bundle
from vera.training.data import file_hash

ROOT = Path(__file__).parents[2]


def test_notebook_is_valid_python_and_keeps_expensive_actions_opt_in():
    path = ROOT / "training/kaggle/vera-qwen35.ipynb"
    notebook = json.loads(path.read_text())
    nbformat.validate(nbformat.read(path, as_version=4))
    assert notebook["nbformat"] == 4
    code = []
    for cell in notebook["cells"]:
        if cell["cell_type"] == "code":
            assert cell["execution_count"] is None
            assert cell["outputs"] == []
            ast.parse(cell["source"])
            code.append(cell["source"])
    assert sum(len(source.splitlines()) for source in code) <= 200
    joined = "\n".join(code)
    for guard in (
        "GPU_COUNT = 1", "RUN_FULL_TRAINING = False", "RUN_FINAL_TEST = False",
        "EXPORT_FORMAT = None", "RUN_SMOKE = False", "RUN_BASELINE = False",
    ):
        assert guard in joined
    assert "--nproc_per_node=2" in joined
    assert "check=True" in joined
    assert "checkpoint.rglob" in joined
    assert "provenance/smoke-report.json" in joined
    assert "SOURCE_TERMS_AND_SAMPLES_REVIEWED" not in joined
    assert "quality['dataset_sha256']" in joined


def test_bundle_only_copies_explicit_files_and_wheel(tmp_path, monkeypatch):
    def build_wheel(command, **kwargs):
        directory = Path(command[4])
        directory.mkdir()
        with zipfile.ZipFile(directory / "vera.whl", "w") as wheel:
            wheel.writestr("vera/__init__.py", "")

    monkeypatch.setattr("vera.training.bundle.shutil.which", lambda command: "/tools/uv")
    monkeypatch.setattr("vera.training.bundle.subprocess.run", build_wheel)
    output = tmp_path / "upload"
    archive = prepare_bundle(
        ROOT, output, counts={"train": 20, "validation": 20, "test": 20},
    )
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert "data/manifest.json" in names
        assert "wheels/vera.whl" in names
        assert "bootstrap.py" in names
        assert json.loads(package.read("bundle.json"))["workflow_version"] == 3
        assert json.loads(package.read("quality-report.json"))["passed"] is True
        assert not any(".env" in name or name.endswith((".db", ".gguf")) for name in names)
    manifest = json.loads((output / "bundle.json").read_text())
    assert all(file_hash(output / name) == value for name, value in manifest["files"].items())
    with pytest.raises(FileExistsError):
        prepare_bundle(ROOT, output)


def test_bundle_rejects_private_files_in_wheel(tmp_path, monkeypatch):
    def build_wheel(command, **kwargs):
        directory = Path(command[4])
        directory.mkdir()
        with zipfile.ZipFile(directory / "vera.whl", "w") as wheel:
            wheel.writestr("vera/.env", "not a real credential")

    monkeypatch.setattr("vera.training.bundle.shutil.which", lambda command: "/tools/uv")
    monkeypatch.setattr("vera.training.bundle.subprocess.run", build_wheel)
    with pytest.raises(ValueError, match="private/runtime"):
        prepare_bundle(ROOT, tmp_path / "unsafe",
                       counts={"train": 20, "validation": 20, "test": 20})
    assert not (tmp_path / "unsafe").exists()


@pytest.mark.parametrize("has_smoke_report", [True, False])
def test_download_cell_preserves_checkpoints_after_interrupted_training(
    tmp_path, has_smoke_report,
):
    notebook = json.loads((ROOT / "training/kaggle/vera-qwen35.ipynb").read_text())
    source = next(cell["source"] for cell in notebook["cells"] if cell["id"] == "download")
    work = tmp_path / "working"
    full = work / "full-1gpu"
    smoke = work / "smoke-1gpu"
    checkpoint = full / "checkpoint-50"
    checkpoint.mkdir(parents=True)
    (checkpoint / "optimizer.pt").write_bytes(b"test optimizer state")
    (full / "recipe.json").write_text("{}")
    smoke.mkdir()
    smoke_report = smoke / "report.json"
    if has_smoke_report:
        smoke_report.write_text('{"passed": true}')
    data = tmp_path / "input/data"
    data.mkdir(parents=True)
    (data / "manifest.json").write_text("{}")
    (data.parent / "quality-report.json").write_text("{}")
    namespace = {
        "FULL": full, "SMOKE": smoke, "WORK": work, "DATA": data,
        "SMOKE_REPORT": smoke_report, "BUNDLE": data.parent,
    }
    exec(compile(source, "kaggle-download-cell", "exec"), namespace)
    archive = tmp_path / "vera-results-full-1gpu.zip"
    with zipfile.ZipFile(archive) as package:
        names = package.namelist()
        assert "full-1gpu/checkpoint-50/optimizer.pt" in names
        assert "provenance/data-manifest.json" in names
        assert ("provenance/smoke-report.json" in names) == has_smoke_report


def test_cli_publishes_a_visible_root_archive_without_overwriting(tmp_path, monkeypatch):
    notebook = tmp_path / "training/kaggle/vera-qwen35.ipynb"
    notebook.parent.mkdir(parents=True)
    notebook.write_text("{}")
    archive = tmp_path / ".vera/bundles/vera-sft-visible.zip"
    archive.parent.mkdir(parents=True)
    archive.write_bytes(b"test bundle")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr("vera.training.bundle.prepare_bundle", lambda *args, **kwargs: archive)
    monkeypatch.setattr("sys.argv", [
        "vera-prepare-kaggle", "--output", ".vera/bundles/vera-sft-visible",
    ])
    main()
    assert (tmp_path / "vera-sft-visible.zip").read_bytes() == archive.read_bytes()
    with pytest.raises(SystemExit):
        main()
