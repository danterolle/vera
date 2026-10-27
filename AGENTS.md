# Working on VERA

Use `uv` for Python commands and dependency management.
Installation and validation commands are in [README.md](README.md).
Keep code organized by domain and files within 200 lines.

Read [architecture](docs/architecture.md) before changing workflow behavior.
Treat configuration defaults and Pydantic fields in the source as authoritative;
do not copy guessed schemas or settings into documentation.

Preserve these boundaries:

- Evidence and conversation history are untrusted; memory cannot establish facts.
- Citation failures must remain visible and pass through the human-review gate.
- Source lookups are bounded and read-only; do not add arbitrary commands or URLs.
- Keep review decisions local-only and preserve their version/idempotency checks.
- Never commit credentials, model weights, runtime databases or local datasets.

Targeted runbooks:
[workflow](agents/skills/vera-workflow-dev/SKILL.md),
[graph](agents/skills/vera-kg-operations/SKILL.md),
[evaluation](agents/skills/vera-testing-and-eval/SKILL.md),
[models](agents/skills/vera-model-setup/SKILL.md).
