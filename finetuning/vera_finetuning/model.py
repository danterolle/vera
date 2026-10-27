from pathlib import Path

from vera_finetuning.data import MODEL_ID, MODEL_REVISION


def build_model(resume: Path | None = None):
    import torch
    from peft import LoraConfig, PeftModel, TaskType, get_peft_model
    from transformers import Qwen3_5ForCausalLM

    if not torch.cuda.is_available() or torch.cuda.device_count() < 2:
        raise RuntimeError("This FP32 model-parallel recipe requires two CUDA GPUs")
    for index in range(2):
        free, _ = torch.cuda.mem_get_info(index)
        if free < 14 * 1024**3:
            raise RuntimeError(f"GPU {index} needs at least 14 GiB free before loading")
    torch.manual_seed(3407)
    base = Qwen3_5ForCausalLM.from_pretrained(
        MODEL_ID,
        revision=MODEL_REVISION,
        dtype=torch.float32,
        device_map="balanced",
        max_memory={0: "11GiB", 1: "11GiB"},
        attn_implementation="eager",
        trust_remote_code=False,
    )
    devices = {
        str(value) if not isinstance(value, int) else f"cuda:{value}"
        for value in base.hf_device_map.values()
    }
    if devices != {"cuda:0", "cuda:1"}:
        raise RuntimeError(f"Expected GPU-only sharding on both devices, got {base.hf_device_map}")
    base.config.use_cache = False
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
