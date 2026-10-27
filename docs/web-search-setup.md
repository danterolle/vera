# Configure bounded online research

VERA uses online research only when both `VERA_LIVE_SOURCES` and
`VERA_WEB_SEARCH_ENABLED` are enabled. It is a bounded evidence-acquisition step,
not an unrestricted browser or a model-controlled search engine.

## Providers

With `VERA_WEB_SEARCH_API_KEY`, VERA first uses Brave Search to discover source URLs.
Without usable Brave results, it tries DuckDuckGo URL discovery and exact lookups in
MITRE ATT&CK software, enterprise-technique and group catalogs.
Exact CVE requests separately use CVE.org, NVD, CISA KEV, FIRST EPSS and OSV.

Search snippets and Instant Answer abstracts are never accepted as source evidence.
VERA retrieves the actual page from an allowlisted HTTPS host and retains its text,
URL and HTTP provenance. At most two pages are retained. The model assesses whether
general web pages concern the requested cybersecurity subject; failed or unavailable
assessment makes those pages unavailable.

All research requests are GET requests, share the run's tool budget and use configured
timeouts. Responses are limited to 2 MiB. Redirects are not followed automatically;
failed retrieval is explicit rather than replaced with a search snippet.
These controls do not establish that every statement on an allowed host is correct.

## Obtain and configure a Brave key

Use the [Brave Search API portal](https://brave.com/search/api/) to create an account
and obtain a search API key. Check its current plans, quotas and charges; VERA does not
guarantee that a free plan is available.

Store configuration in the local, ignored `.env`, never in a tracked file:

```dotenv
VERA_LIVE_SOURCES=true
VERA_WEB_SEARCH_ENABLED=true
VERA_WEB_SEARCH_API_KEY=REPLACE_WITH_YOUR_BRAVE_API_KEY
VERA_REACT_ENABLED=false
```

Omit `VERA_WEB_SEARCH_API_KEY` to use only keyless discovery and catalogs.
Restart the local VERA process after changing configuration:

```bash
uv run --extra knowledge-graph vera serve
```

## Trigger research and inspect provenance

Explicit online requests, requests for current information, and missing local subject
coverage can activate research. A follow-up asking to search online can resolve the
subject from the previous user question.

For example:

```bash
curl -fsS http://127.0.0.1:8000/v1/analyze \
  -H 'Content-Type: application/json' \
  -d '{"query":"Search online for current information about LockBit.","origin":"chat"}'
```

Open `/chat` and expand the response's source details. Inspect `lookup_method`,
`provenance`, retrieval time, source URL and actual HTTP requests. A selected tools route
does not prove a network request happened: inspect `metrics.tool_calls`.
An HTTP `202` response is an unpublished review, not a completed report.

Missing source pages, rate limits, disabled access and depleted budgets remain explicit
unavailable results. Stored graph records are cached evidence, not fresh online lookups.
Approving a draft publishes it; approval does not independently verify its statements.
