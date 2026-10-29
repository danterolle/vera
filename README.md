# VERA

Evidence-based cybersecurity analysis prototype using LangGraph, local retrieval,
an optional Kuzu knowledge graph and a local language model. It analyzes structured
events, checks citations and holds uncertain or high-risk reports for human review.
An alert is not proof of compromise.

## Quick start

Requires Python 3.11+ and [uv](https://docs.astral.sh/uv/).
From the repository root:

```bash
uv sync --extra dev --extra knowledge-graph
cp -n .env.example .env
uv run --extra knowledge-graph vera kg-build
VERA_LLM_PROVIDER=deterministic VERA_LIVE_SOURCES=false \
  uv run --extra knowledge-graph vera serve --open-browser
```

This starts without a model server or live lookups. The deterministic provider
extracts findings from evidence; it does not provide open-ended model reasoning.
The copy preserves an existing `.env`.

| Address | Purpose |
| --- | --- |
| <http://127.0.0.1:8000/chat> | Questions, sources and human review |
| <http://127.0.0.1:8000/knowledge-graph> | Domain graph |
| <http://127.0.0.1:8000/docs> | Interactive API reference |

Stop VERA with Ctrl+C. Configuration, models, databases and downloaded data are local
and excluded from Git; cloning the repository does not reproduce them.

## Use a local model

Follow [local model setup](docs/local-model.md) for Qwen3.5-4B with LM Studio/Bionic
or `llama-server`, then start VERA without the quick-start environment overrides:

```bash
uv run --extra knowledge-graph vera serve --open-browser
```

The model server is a separate process. Check `metadata.model`,
`metadata.provider_fallback` and response warnings to verify that it answered.
`/health` reports configuration, not successful inference.

## CLI

```bash
uv run --extra knowledge-graph vera analyze "Explain PowerShell" --offline --json
uv run --extra knowledge-graph vera analyze "Analyze this traffic" \
  --events src/vera/data/samples/port-scan.jsonl --simulated --offline --json
```

Use `--pcap capture.pcap` instead of `--events` when `tshark` is installed.
Raw log text in a question does not run detectors. `--offline` disables source
lookups, not local model calls. Exit code `2` means a draft requires review.

## Development

```bash
uv run --extra dev --extra knowledge-graph ruff check .
VERA_LLM_PROVIDER=deterministic VERA_KG_ENABLED=false \
  uv run --extra knowledge-graph vera evaluate --json
```

CI runs Ruff. The bundled evaluation is an offline synthetic benchmark, not an
automated test suite or a guarantee of model accuracy.

## Documentation

- [Chat, API and human review](docs/chat.md)
- [Architecture, evidence and limits](docs/architecture.md)
- [Knowledge graph](docs/knowledge-graph.md)
- [Local models](docs/local-model.md)
- [Kaggle pilot and retained dataset](docs/kaggle-finetuning.md)
- [Fine-tuning preview: answer-contract behavior](docs/finetuning-preview-20261028.md)

The Kaggle pilot is experimental. The retained dataset predates the chat prompt
and is rejected until a compatible dataset is prepared and reviewed.
