# VERA

VERA is a prototype for evidence-based cybersecurity analysis. It combines a local
language model with retrieval, a LangGraph workflow and an optional Kuzu knowledge
graph. Given a question or structured events, it gathers evidence, checks citations
and sends uncertain or high-risk drafts to a person for review. An alert alone is
never treated as proof of compromise.

## Quick start

You need Python 3.11 or later and [uv](https://docs.astral.sh/uv/).
Run these commands from the repository root:

```bash
uv sync --extra dev --extra knowledge-graph
cp -n .env.example .env
uv run --extra knowledge-graph vera kg-build
VERA_LLM_PROVIDER=deterministic VERA_LIVE_SOURCES=false \
  uv run --extra knowledge-graph vera serve --open-browser
```

This setup works without a model server or live lookups. Its deterministic provider
extracts findings from evidence rather than generating open-ended analysis. The
`cp -n` command leaves an existing `.env` untouched.

Responses are in English by default. Change `VERA_RESPONSE_LANGUAGE` to choose another
response language; quoted evidence always keeps its original wording and language.

| Address | Purpose |
| --- | --- |
| <http://127.0.0.1:8000/chat> | Questions, sources and human review |
| <http://127.0.0.1:8000/knowledge-graph> | Domain graph |
| <http://127.0.0.1:8000/docs> | Interactive API reference |

Press Ctrl+C to stop VERA. Configuration, models, databases and downloaded data stay
on your machine and are excluded from Git, so a clone does not include them.

## Use a local model

To use Qwen3.5-4B, follow the [local model guide](docs/local-model.md) for
LM Studio/Bionic or `llama-server`. Then start VERA without the quick-start overrides:

```bash
uv run --extra knowledge-graph vera serve --open-browser
```

The model server runs separately from VERA. Check `metadata.model`,
`metadata.provider_fallback` and the response warnings to confirm which provider
answered. A successful `/health` response describes configuration, not inference.

## CLI

```bash
uv run --extra knowledge-graph vera analyze "Explain PowerShell" --offline --json
uv run --extra knowledge-graph vera analyze "Analyze this traffic" \
  --events src/vera/data/samples/port-scan.jsonl --simulated --offline --json
```

If `tshark` is installed, you can pass `--pcap capture.pcap` instead of `--events`.
Pasting log text into a question does not run the detectors. The `--offline` flag
disables source lookups, but still allows local model calls. Exit code `2` means
the draft is waiting for human review.

## Development

```bash
uv run --extra dev --extra knowledge-graph ruff check .
VERA_LLM_PROVIDER=deterministic VERA_KG_ENABLED=false \
  uv run --extra knowledge-graph vera evaluate --json
```

CI runs Ruff. The bundled evaluation exercises offline synthetic scenarios; it is
neither an automated test suite nor evidence of general model accuracy.

## Documentation

- [Chat, API and human review](docs/chat.md)
- [Architecture, evidence and limits](docs/architecture.md)
- [Knowledge graph](docs/knowledge-graph.md)
- [Local models](docs/local-model.md)
- [Kaggle training and evaluation](docs/kaggle-finetuning.md)
- [Fine-tuning preview: answer-contract behavior](docs/finetuning-preview-20261028.md)
- [Fine-tuning run: step 400 and the perturbed evaluation](docs/finetuning-run-20261101.md)
- [Step-400 adapter: purpose, evidence and limits](docs/finetuning-adapter-assessment.md)

The v4 adapter follows the measured answer contract more reliably, but that does not
establish incident-analysis accuracy or authorize deployment. Under runtime contract
`vera-evidence-v2`, VERA checks each cited record, retains failures after repair and
requires review of non-extractive model summaries and fallbacks. Acceptance of this
runtime still needs fresh independent answers and a real human sign-off.
