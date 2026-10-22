import json

import pytest

from vera.training.arguments import (
    assert_matching_recipe,
    recipe,
    training_arguments,
)
from vera.training.build import build_dataset
from vera.training.data import encode_record, read_records
from vera.training.records import context_from_prompt
from vera.training.scoring import score_answer
from vera.training.train import _check_inputs


@pytest.fixture
def record(tmp_path):
    build_dataset(tmp_path / "data", counts={"train": 20, "validation": 20, "test": 20})
    return next(item for item in read_records(tmp_path / "data", "train")
                if item.task == "grounded"
                and len(context_from_prompt(item.messages[1].content)["evidence"]) > 1)


class CharacterTokenizer:
    def apply_chat_template(self, messages, *, add_generation_prompt, **kwargs):
        assert kwargs["return_dict"] is False
        prefix = "<assistant>"
        if add_generation_prompt:
            return list(prefix.encode())
        return list((prefix + messages[-1]["content"] + "<eos>").encode())


def test_assistant_loss_mask_and_no_truncation(record):
    encoded = encode_record(record, CharacterTokenizer(), 8192)
    prefix_length = len("<assistant>")
    assert encoded["labels"][:prefix_length] == [-100] * prefix_length
    assert encoded["labels"][prefix_length:] == encoded["input_ids"][prefix_length:]
    with pytest.raises(ValueError, match="truncation is disabled"):
        encode_record(record, CharacterTokenizer(), 256)


def test_invalid_template_boundary_is_rejected(record):
    class BrokenTokenizer(CharacterTokenizer):
        def apply_chat_template(self, messages, *, add_generation_prompt, **kwargs):
            return [1] if add_generation_prompt else [2, 3]

    with pytest.raises(ValueError, match="loss mask"):
        encode_record(record, BrokenTokenizer(), 2048)


def test_raw_scoring_accepts_gold_but_rejects_broken_quotes_and_empty_answers(record):
    gold = record.messages[2].content
    assert score_answer(gold, record)["passed"]
    payload = json.loads(gold)
    payload["claims"][0]["citations"][0]["supporting_quote"] = "Invented supporting text."
    broken = score_answer(json.dumps(payload), record)
    assert broken["json_valid"] and not broken["contract_valid"]
    assert broken["error"]
    payload["claims"] = []
    assert not score_answer(json.dumps(payload), record)["passed"]
    assert not score_answer(gold, record, truncated=True)["passed"]
    assert not score_answer("not json", record)["json_valid"]


def test_scoring_rejects_coerced_scope_flags(record):
    payload = json.loads(record.messages[2].content)
    payload["out_of_scope"] = "false"
    assert not score_answer(json.dumps(payload), record)["contract_valid"]


def test_scoring_rejects_facts_from_an_unrelated_distractor(record):
    payload = json.loads(record.messages[2].content)
    correct = payload["claims"][0]["evidence_ids"][0]
    distractor = next(item for item in context_from_prompt(record.messages[1].content)["evidence"]
                      if item["id"] != correct)
    claim = payload["claims"][0]
    claim["text"] = distractor["content"][:800]
    claim["evidence_ids"] = [distractor["id"]]
    claim["citations"] = [{
        "evidence_id": distractor["id"], "supporting_quote": claim["text"],
    }]
    result = score_answer(json.dumps(payload), record)
    assert result["contract_valid"]
    assert not result["factual_source_match"] and not result["passed"]


def test_ddp_keeps_effective_batch_and_full_training_requires_smoke(monkeypatch):
    arguments = ["--data", "data", "--output", "output"]
    monkeypatch.setenv("WORLD_SIZE", "1")
    assert training_arguments(arguments).accumulation == 8
    monkeypatch.setenv("WORLD_SIZE", "2")
    assert training_arguments(arguments).accumulation == 4
    with pytest.raises(SystemExit):
        training_arguments(arguments + ["--mode", "train"])
    with pytest.raises(SystemExit):
        training_arguments(arguments + ["--accumulation", "0"])


def test_recipe_matching_rejects_changed_context_and_model_revision():
    args = training_arguments(["--data", "data", "--output", "output"])
    original = recipe(args, "dataset-hash")
    full = {**original, "mode": "train", "steps": None}
    assert_matching_recipe(full, original, smoke=True)
    for changed in (
        {**original, "max_length": 1024},
        {**original, "revision": "other-model"},
        {**original, "manifest_sha256": "other-data"},
        {**original, "world_size": 2},
    ):
        with pytest.raises(ValueError, match="different training recipe"):
            assert_matching_recipe(changed, original, smoke=True)


def test_resume_requires_optimizer_scheduler_and_rng_state(tmp_path, monkeypatch):
    monkeypatch.setenv("WORLD_SIZE", "1")
    checkpoint = tmp_path / "checkpoint-10"
    checkpoint.mkdir()
    args = training_arguments([
        "--data", "data", "--output", str(tmp_path / "out"),
        "--resume", str(checkpoint),
    ])
    configuration = recipe(args, "dataset-hash")
    (checkpoint / "recipe.json").write_text(json.dumps(configuration))
    (checkpoint / "trainer_state.json").write_text("{}")
    with pytest.raises(ValueError, match="complete Trainer checkpoint"):
        _check_inputs(args, configuration)
    for name in ("optimizer.pt", "scheduler.pt", "rng_state.pth",
                 "adapter_config.json", "adapter_model.safetensors"):
        (checkpoint / name).touch()
    _check_inputs(args, configuration)
