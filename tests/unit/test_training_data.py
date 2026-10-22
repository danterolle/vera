import json
from itertools import combinations

import pytest

from vera.training.build import build_dataset
from vera.training.data import read_records, verify_dataset
from vera.training.records import (
    context_from_prompt,
    semantic_fingerprint,
    validate_record,
)
from vera.training.sources import bundled_groups, split_groups


@pytest.fixture
def training_data(tmp_path):
    directory = tmp_path / "data"
    manifest = build_dataset(directory, counts={"train": 60, "validation": 20, "test": 20})
    return directory, manifest


def test_dataset_targets_are_grounded_and_cover_all_claim_statuses(training_data):
    directory, manifest = training_data
    statuses = set()
    signatures = set()
    for split, information in manifest["splits"].items():
        records = read_records(directory, split)
        assert len(records) == information["examples"]
        assert len({record.task for record in records}) == 9
        for record in records:
            validate_record(record)
            assert record.origin == "synthetic_template"
            signature = semantic_fingerprint(record)
            assert signature not in signatures
            signatures.add(signature)
            answer = json.loads(record.messages[2].content)
            statuses.update(claim["status"] for claim in answer["claims"])
            context = context_from_prompt(record.messages[1].content)
            if record.task == "simulated":
                assert all(item["status"] == "simulated" for item in context["evidence"])
                assert context["route"] == ("FULL" if context["alerts"] else "STREAM")
            if record.task == "memory_only":
                assert all(item["source"] == "memory" for item in context["evidence"])
                assert all(claim["status"] == "unavailable" for claim in answer["claims"])
    assert statuses == {"supported_fact", "system_inference", "unavailable", "simulated"}
    assert manifest["human_reviewed"] is False


def test_sources_and_entity_families_are_split_before_augmentation():
    groups, excluded = bundled_groups()
    assert excluded > 0
    assert sum(len(group.documents) for group in groups) > 50
    partitions = split_groups(groups, 3407)
    for first, second in combinations(partitions.values(), 2):
        first_keys = set().union(*(group.keys for group in first))
        second_keys = set().union(*(group.keys for group in second))
        assert not first_keys & second_keys
    assert any("entity:T1059" in group.keys for group in groups)


def test_generation_is_byte_reproducible_and_independent_of_runtime_data(tmp_path, monkeypatch):
    monkeypatch.setenv("VERA_DB_PATH", str(tmp_path / "must-not-be-read.db"))
    monkeypatch.setenv("VERA_CORPUS_DIR", str(tmp_path / "private-corpus"))
    for name in ("first", "second"):
        build_dataset(
            tmp_path / name, counts={"train": 40, "validation": 20, "test": 20},
        )
    first, second = tmp_path / "first", tmp_path / "second"
    assert sorted(path.relative_to(first) for path in first.rglob("*") if path.is_file()) == sorted(
        path.relative_to(second) for path in second.rglob("*") if path.is_file()
    )
    for path in first.rglob("*"):
        if path.is_file():
            assert path.read_bytes() == (second / path.relative_to(first)).read_bytes()
    assert not (tmp_path / "must-not-be-read.db").exists()


def test_checksum_tampering_and_output_reuse_fail(training_data):
    directory, _ = training_data
    with pytest.raises(FileExistsError):
        build_dataset(directory)
    shard = next((directory / "train").glob("*.jsonl"))
    shard.write_text(shard.read_text() + "\n")
    with pytest.raises(ValueError, match="checksum"):
        verify_dataset(directory)


def test_stratified_small_selection_preserves_all_tasks(training_data):
    directory, _ = training_data
    records = read_records(directory, "train", limit=18)
    assert len(records) == 18
    assert len({record.task for record in records}) == 9


def test_build_rejects_invalid_sizes(tmp_path):
    with pytest.raises(ValueError, match="at least 20"):
        build_dataset(tmp_path / "invalid", counts={"train": 0, "validation": 20, "test": 20})
