import json

import pytest

from vera.training.audit import audit_dataset
from vera.training.build import build_dataset
from vera.training.data import file_hash
from vera.training.records import fingerprint


def test_audit_covers_all_examples_and_both_stream_outcomes(tmp_path):
    data = tmp_path / "data"
    build_dataset(data, counts={"train": 40, "validation": 20, "test": 20})
    report = audit_dataset(data)
    assert report["passed"] is True
    assert report["human_reviewed"] is False
    for split, counts in (("train", (4, 2)), ("validation", (2, 1)), ("test", (2, 1))):
        result = report["splits"][split]
        assert result["streams"]["with_alerts"] == counts[0]
        assert result["streams"]["without_alerts"] == counts[1]


def test_audit_rejects_a_fabricated_source_even_with_valid_quotes_and_checksums(tmp_path):
    data = tmp_path / "data"
    build_dataset(data, counts={"train": 20, "validation": 20, "test": 20})
    shard = data / "train/part-000.jsonl"
    records = [json.loads(line) for line in shard.read_text().splitlines()]
    record = next(item for item in records if item["task"] == "grounded")
    prompt = record["messages"][1]["content"]
    prefix, encoded = prompt.split("\n", 1)
    context = json.loads(encoded)
    answer = json.loads(record["messages"][2]["content"])
    identifier = answer["claims"][0]["evidence_ids"][0]
    evidence = next(item for item in context["evidence"] if item["id"] == identifier)
    evidence["content"] = "Fabricated security information."
    answer["claims"][0]["text"] = evidence["content"]
    answer["claims"][0]["citations"][0]["supporting_quote"] = evidence["content"]
    record["messages"][1]["content"] = prefix + "\n" + json.dumps(context)
    record["messages"][2]["content"] = json.dumps(answer)
    record["id"] = fingerprint(record["messages"])
    shard.write_text("".join(json.dumps(item) + "\n" for item in records))
    path = data / "manifest.json"
    manifest = json.loads(path.read_text())
    manifest["files"]["train/part-000.jsonl"] = file_hash(shard)
    path.write_text(json.dumps(manifest))
    with pytest.raises(ValueError, match="not from a bundled source"):
        audit_dataset(data)
