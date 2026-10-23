import json

import pytest

from vera.training.check_runtime import main


def test_failed_runtime_check_is_reported_and_not_masked(tmp_path, monkeypatch):
    output = tmp_path / "runtime-check.json"
    monkeypatch.setattr("sys.argv", ["check-runtime", "--output", str(output)])

    def fail():
        raise RuntimeError("CUDA driver is unavailable")

    monkeypatch.setattr("vera.training.check_runtime.check_runtime", fail)
    with pytest.raises(RuntimeError, match="CUDA driver"):
        main()
    report = json.loads(output.read_text())
    assert report["passed"] is False
    assert "CUDA driver" in report["error"]


def test_runtime_report_does_not_overwrite_previous_results(tmp_path, monkeypatch):
    output = tmp_path / "runtime-check.json"
    output.write_text('{"passed": false}')
    monkeypatch.setattr("sys.argv", ["check-runtime", "--output", str(output)])
    with pytest.raises(SystemExit):
        main()
    assert output.read_text() == '{"passed": false}'
