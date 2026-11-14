---
name: vera-model-setup
description: >-
  Configure or diagnose VERA's Qwen, LM Studio/Bionic and llama-server connections.
---

# Local model setup

Use the [local model guide](../../../docs/local-model.md) rather than copying its
profile settings into another document. The model server and VERA run as separate
processes, normally on ports 1234 and 8000. Read the exact model ID from `/v1/models`;
a display name or GGUF filename may not be the API identifier.

To confirm inference, inspect `metadata.model`, `metadata.provider_fallback`, warnings
and citations in an actual answer. `/health` only describes configuration, and HTTP
`202` may mean that a valid draft is waiting for review. Keep credentials local, and
leave existing model files and runtime installations intact.
