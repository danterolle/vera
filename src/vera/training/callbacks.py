import hashlib
import math
from pathlib import Path

from transformers import TrainerCallback

from vera.training.runtime import save_json


def parameter_digest(model) -> str:
    digest = hashlib.sha256()
    for name, parameter in model.named_parameters():
        if parameter.requires_grad:
            digest.update(name.encode())
            digest.update(parameter.detach().float().cpu().contiguous().numpy().tobytes())
    return digest.hexdigest()


class TrainingGuard(TrainerCallback):
    def __init__(self, configuration: dict) -> None:
        self.configuration = configuration
        self.updates = 0
        self.nonzero_gradients = 0
        self.before = ""
        self.after = ""

    def on_train_begin(self, args, state, control, **kwargs):
        self.before = parameter_digest(kwargs["model"])

    def on_pre_optimizer_step(self, args, state, control, **kwargs):
        import torch

        gradients = [
            parameter.grad.detach().float().norm()
            for parameter in kwargs["model"].parameters()
            if parameter.requires_grad and parameter.grad is not None
        ]
        if not gradients:
            raise RuntimeError("No trainable gradients were produced")
        norm = float(torch.stack(gradients).norm().cpu())
        if not math.isfinite(norm):
            raise RuntimeError("Non-finite gradients detected; training stopped")
        self.nonzero_gradients += int(norm > 0)
        self.updates += 1

    def on_log(self, args, state, control, logs=None, **kwargs):
        for name in ("loss", "eval_loss", "grad_norm"):
            if logs and name in logs and not math.isfinite(float(logs[name])):
                raise RuntimeError(f"Non-finite {name} detected; training stopped")

    def on_save(self, args, state, control, **kwargs):
        if state.is_world_process_zero:
            save_json(
                Path(args.output_dir) / f"checkpoint-{state.global_step}" / "recipe.json",
                self.configuration,
            )

    def on_train_end(self, args, state, control, **kwargs):
        self.after = parameter_digest(kwargs["model"])

    def assert_updated(self) -> None:
        if not self.updates or not self.nonzero_gradients or self.before == self.after:
            raise RuntimeError("Training did not produce a verified adapter weight update")
