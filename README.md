# VERA

VERA is a reproducible teaching prototype for evidence-based cybersecurity analysis. It
uses deterministic routing, curated knowledge, local retrieval, restricted live lookups,
event-stream rules, claim validation, reflection, and persistent memory. It is not a SOC
platform and does not establish that a compromise occurred.

## Routes

| Route | Activated context |
| --- | --- |
| `CAG_ONLY` | Stable curated cybersecurity knowledge |
| `CAG_RAG` | Curated knowledge and local authoritative corpus |
| `CAG_RAG_TOOL` | Local context and exact CVE.org, NVD, CISA KEV, EPSS, and OSV lookups |
| `STREAM` | Deterministic analysis of normalized events without triggered attack rules |
| `FULL` | Composite stream, retrieval, and API analysis or detected attack signals |

Deterministic rules select clear requests. An enabled LLM only resolves ambiguous requests
and generates from already assembled evidence. LangGraph bounds generation to two attempts.
Internally, a compositional `ResourcePlan` selects CAG, RAG, APIs, and stream independently;
the route name remains a derived compatibility label.

## Requirements

- Python 3.11 or newer
- `uv`
- Optional: `tshark` for PCAP replay
- Optional: Ollama, an OpenAI-compatible endpoint, or Gemini

## Install

```bash
uv sync --extra dev
cp .env.example .env
```

The default hash embedding backend is deterministic and requires no model download. To use
local Sentence Transformers:

```bash
uv sync --extra dev --extra embeddings
VERA_EMBEDDING_BACKEND=sentence-transformers uv run vera evaluate
```

## CLI

```bash
uv run vera analyze "What is defense in depth?" --offline
uv run vera analyze "Analyze CVE-2021-44228" --json
uv run vera analyze "Analyze this controlled replay" \
  --events src/vera/data/samples/network-events.jsonl --simulated --offline
uv run vera evaluate
uv run vera history
uv run vera corpus-status
```

### Synthetic event samples

The bundled JSONL streams isolate both negative and positive detector paths:

| File | Expected outcome |
| --- | --- |
| `benign-web.jsonl` | `STREAM`, no alerts |
| `port-scan.jsonl` | Network service discovery |
| `http-brute-force.jsonl` | Repeated authentication failures |
| `syn-flood.jsonl` | High-volume TCP SYN activity |
| `web-exploitation.jsonl` | JNDI, traversal, and command-injection patterns |
| `network-events.jsonl` | Combined incident replay |

All records use private or documentation-only addresses and are marked as simulated.

For PCAP input, VERA executes `tshark` directly with a fixed field allowlist, a packet limit,
a timeout, and no shell:

```bash
uv run vera analyze "Analyze this capture" --pcap capture.pcap --offline
```

## HTTP API

```bash
uv run vera serve
curl -s http://127.0.0.1:8000/health
curl -s http://127.0.0.1:8000/v1/analyze \
  -H 'content-type: application/json' \
  -d '{"query":"Explain MITRE ATT&CK T1190"}'
```

OpenAPI documentation is available at `http://127.0.0.1:8000/docs`.

### LangGraph browser

Start the API and open the dependency-free local workflow viewer:

```bash
uv run vera serve --open-browser
```

The page at `http://127.0.0.1:8000/graph` reads the compiled topology from
`graph.get_graph()`. It shows every node and conditional edge, exposes LangGraph's Mermaid
source, and highlights the path and retry count of a selected persisted run. The machine
readable representation is available from `/v1/graph`.

## Corpus

The bundled offline corpus contains more than 60 focused documents from MITRE ATT&CK, CWE,
CAPEC, OWASP, NIST, and selected NVD snapshots. Retrieval combines normalized BM25 and local
vector similarity, retaining both component scores in evidence metadata.

Synchronize the complete current Enterprise ATT&CK STIX collection and CISA KEV catalog:

```bash
uv run vera corpus-sync
uv run vera corpus-sync --feed mitre-attack
uv run vera corpus-sync --feed cisa-kev
uv run vera corpus-status
```

Synchronization uses fixed official URLs, response-size and document-count limits, schema
validation, and atomic local replacement under `.vera/corpus`. It never runs implicitly.

## LLM providers

The deterministic provider is the reliable default and produces fully structured answers
without network access. External providers receive only normalized context and must return
schema-valid JSON.

### Ollama or Unsloth

```bash
export VERA_LLM_PROVIDER=ollama
export VERA_LLM_MODEL=llama3.1:8b
export VERA_LLM_BASE_URL=http://localhost:11434
uv run vera analyze "Assess the available security context"
```

Any OpenAI-compatible endpoint can use `VERA_LLM_PROVIDER=openai` and
`VERA_LLM_API_KEY` when required.

### Gemini

```bash
export VERA_LLM_PROVIDER=gemini
export VERA_LLM_MODEL=gemini-2.5-flash
export VERA_GEMINI_API_KEY=your-key
```

If generation fails, the result contains a warning and uses deterministic rendering. Failed
source requests become explicit unavailable evidence rather than fabricated values.
Live CVE sources execute concurrently within the configured tool budget, and skipped lookups
are emitted as unavailable evidence.

## Evidence status

| Status | Meaning |
| --- | --- |
| `supported_fact` | Grounded by a verbatim quote from available non-memory evidence |
| `system_inference` | Derived by routing, detection, memory, or model reasoning |
| `unavailable` | Required data was disabled, absent, or failed |
| `simulated` | Derived from an explicitly simulated event stream |

Bundled CVE records are marked as snapshots. Persistent semantic and episodic memories can
inform later runs, but the validator never accepts memory as authoritative support.
Every supported fact must also include a verbatim quotation that passes conservative grounding
checks for meaningful terms, identifiers, numbers, and negation.

## Quality commands

```bash
uv run ruff check .
uv run pytest
uv run vera evaluate --json
```

See [architecture](docs/architecture.md) and [data provenance](docs/data-provenance.md) for
the workflow contract, source boundaries, and known limitations.
