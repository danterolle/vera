from pathlib import Path

from vera_finetuning.inference import load_base_model


def build_model(resume: Path | None = None):
    import torch
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model

    base = load_base_model()
    if resume is not None:
        model = PeftModel.from_pretrained(base, resume, is_trainable=True)
    else:
        model = get_peft_model(base, LoraConfig(
            task_type=TaskType.CAUSAL_LM,
            r=8,
            lora_alpha=16,
            lora_dropout=0.0,
            bias="none",
            target_modules=[
                "q_proj", "k_proj", "v_proj", "o_proj",
                "gate_proj", "up_proj", "down_proj",
            ],
        ))
    model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={"use_reentrant": False})
    model.enable_input_require_grads()
    if any(parameter.dtype != torch.float32 for parameter in model.parameters()):
        raise RuntimeError("Unexpected reduced-precision weights in the conservative FP32 recipe")
    model.print_trainable_parameters()
    return model
