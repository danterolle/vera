"""Inference-only loading for the pinned base model."""

def load_base_model():
    import torch
    from transformers import Qwen3_5ForCausalLM

    from vera_finetuning.data import MODEL_ID, MODEL_REVISION

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
    return base
