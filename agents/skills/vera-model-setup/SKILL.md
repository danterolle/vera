---
name: vera-model-setup
description: >-
  Configure or diagnose VERA's Qwen, LM Studio/Bionic and llama-server connections.
---

# Local model setup

Follow [local models](../../../docs/local-model.md); do not duplicate profile settings.
The model server and VERA are separate processes, normally on ports 1234 and 8000.
Obtain the exact model ID from `/v1/models`, not a display name or GGUF filename.

Check `metadata.model`, `metadata.provider_fallback`, warnings and citations on an
actual response. `/health` is configuration-only and HTTP `202` can be a valid held review.
Keep credentials local and leave existing model files and runtime installations intact.
