import json
from pathlib import Path


def save_checkpoint(model, tokenizer, optimizer, output: Path, progress: dict) -> Path:
    import torch

    destination = output / f"checkpoint-{progress['steps']:06d}"
    staging = output / f".checkpoint-{progress['steps']:06d}"
    staging.mkdir()
    model.save_pretrained(staging, safe_serialization=True)
    tokenizer.save_pretrained(staging)
    torch.save({
        "optimizer": optimizer.state_dict(),
        "rng_cpu": torch.get_rng_state(),
        "rng_cuda": torch.cuda.get_rng_state_all(),
    }, staging / "training-state.pt")
    (staging / "progress.json").write_text(json.dumps(progress, indent=2) + "\n")
    staging.rename(destination)
    return destination


def restore_checkpoint(optimizer, resume: Path, expected: dict) -> dict:
    import torch

    progress = json.loads((resume / "progress.json").read_text())
    for key in ("archive_sha256", "system_prompt_sha256", "mode", "accumulation", "model_revision"):
        if progress[key] != expected[key]:
            raise ValueError(f"Checkpoint configuration mismatch: {key}")
    state = torch.load(resume / "training-state.pt", map_location="cpu", weights_only=True)
    optimizer.load_state_dict(state["optimizer"])
    torch.set_rng_state(state["rng_cpu"])
    torch.cuda.set_rng_state_all(state["rng_cuda"])
    return progress
