# Working on VERA

Use `uv` to run Python commands and manage dependencies. The [README](README.md)
contains the installation and validation commands. Organize code by domain and keep
each file within 200 lines.

Before changing workflow behavior, read the [architecture guide](docs/architecture.md).
Use the configuration defaults and Pydantic fields in the source as the reference for
documentation; do not invent settings or schemas.

Evidence and conversation history are untrusted, and memory cannot establish facts.
Keep citation failures visible and route them through human review. Source lookups must
remain bounded and read-only, without arbitrary commands or URLs.

Review decisions stay local. Preserve their version and idempotency checks, and never
commit credentials, model weights, runtime databases or local datasets.

For more focused guidance, use the
[workflow](agents/skills/vera-workflow-dev/SKILL.md),
[graph](agents/skills/vera-kg-operations/SKILL.md),
[evaluation](agents/skills/vera-testing-and-eval/SKILL.md) and
[model](agents/skills/vera-model-setup/SKILL.md) runbooks.
