# Workflow Explorer

Start `vera serve` and open **http://127.0.0.1:8000/graph**. The page visualizes the compiled
LangGraph execution workflow, reading nodes/edges from `/v1/graph`; it does not visualize
the domain knowledge stored in Kuzu. Both viewers use custom local HTML/CSS/JavaScript/SVG,
with no external rendering service.

## Run a question

Enter a cybersecurity question under **Analyze** and click **Run analysis**.
The page submits the question to `/v1/analyze`, shows the assessment, findings, cited sources,
model/fallback, and warnings, then selects its saved workflow below **only when the API
returns a completed report (200)**. If the API returns a pending review (202), the page
shows an **unpublished draft** instead; it does not select a saved execution or offer a
saved-report link for that draft. No model is called when you click a route preview.
Select a recorded execution in the header to reopen its saved answer; **Open full saved
report** shows the structured API result. Normalized events require the API or CLI;
PCAP requires the CLI and `tshark`. The model server must be running for model-generated
answers.

## Review an unpublished draft

**Human review** lists open reviews from `/v1/reviews` on page load and when you click
**Refresh open reviews**, including after a server restart. Select one to load the
latest record from `/v1/reviews/{run_id}`. The panel shows the review reasons, query and
route, draft summary and claims with cited quotes, evidence content and availability,
incident alert severities, reflection gaps and completeness (coverage, not accuracy),
warnings, previous reviewer feedback, and revision count. Draft text is not a final
assessment and pending reviews are not listed under **Recorded execution**.

**Approve and publish** saves the completed report, opens it in Analyze, and selects
its recorded workflow. **Reject draft** does not publish it. **Request revision** leaves
the draft pending and displays the updated version and reviewer history. Feedback is
required for reject and revise; it is optional for approve. **Request revision** is hidden
when the server reports that another revision is unavailable. Decisions carry the displayed
version and a unique decision ID. If a version conflict occurs, the panel reloads the
latest draft before another decision. For an unavailable service, the panel retains the
draft and feedback; retrying the unchanged decision reuses its ID. Authorization,
missing-record, and validation errors appear in the panel. Refresh the open list if
the server was restarted or another reviewer acted.

If restart recovery reports an **error** review, normal approve/reject/revise controls
are unavailable. When a previous decision is recoverable, **Retry previous decision**
submits exactly the action, version, feedback, and decision ID supplied by the server.
If no decision can be retried, the error is displayed without action controls.

## Modes and interaction

- **Overview** shows all available nodes and conditional connections.
- **Preview a route** highlights one possible acquisition path. The route buttons and
  context cards select a preview; this does not execute an analysis or call an API.
- **Recorded execution** selects a completed analysis from SQLite. Highlights and metrics
  describe that saved run, not a live debugger or streaming execution.
- Click any node to inspect its role, input/output contracts, and path state. In a recorded
  run, context-card clicks inspect the node without replacing the selected execution.
- **Focus path** dims inactive branches; zoom, drag-to-pan, and **Fit** control the canvas.
- **Raw LangGraph Mermaid** exposes the underlying compiled topology as text.

## Reading the workflow

`START → Normalize input → Meta-controller` initializes the request, detects events,
recalls memory, and chooses a resource plan. The plan selects one acquisition branch:

| Branch | Acquired context |
| --- | --- |
| CAG | Stable curated knowledge and memory |
| RAG | Curated knowledge plus local retrieval; optional Kuzu retrieval |
| RAG + APIs | Local context plus exact authoritative CVE lookups |
| Stream | Normalized stream statistics and evidence, without triggered alerts |
| Full | Stream detections combined with retrieval and exact CVE lookups |

The branches converge on **Generate answer**. There is no direct controller-to-generation
edge: context acquisition lies between them. With ReAct enabled, **Choose action** and
**Observe result** additionally represent bounded evidence acquisition before generation.
The preview shows the finish path; the saved execution also shows tool loops actually used.

**Validate claims** checks evidence references and supporting quotations. Its return edge
to generation allows a bounded repair. **Reflect** records completeness and evidence gaps.
**Review assessment** then chooses either the normal completion path or a human review
pause. An approved review continues to **Persist result**; a rejected review ends without
publishing, and a revision returns through validation. Route previews illustrate the
normal completion path, not a claim that a draft passed human review. **Persist result**
saves the completed report before `END` returns it.

## Metrics and limits

A selected run shows its route, total latency, model/tool call counts, retrieved evidence,
source count, warnings, and the reflection completeness score. Completeness measures the
prototype's evidence coverage, not factual accuracy. A preview has no measured latency or
quality score or measured invocation counts; its highlights illustrate a possible path.

Execution highlights are reconstructed from the saved route and trace counters. Node
descriptions/contracts are explanatory metadata; they are not each node's actual input or
output payload. This view helps understand routing, compare resource use, and inspect
generation/validation retries. It does not prove graph evidence was cited: inspect
`metadata.knowledge_graph.cited_evidence_ids` in the analysis result for that check.

## Manual check

```bash
vera analyze "Explain MITRE ATT&CK T1059.001" --offline
vera analyze "Analyze CVE-2021-44228" --offline
vera serve
```

Open `/graph`. Select **RAG + APIs** and confirm both controller→context and
context→generation connections are visible. Click **RAG retrieval** to select its preview
and inspector. Then select one of the recorded analyses: route and metrics should reflect
that saved result. The API is `/v1/graph?run_id=<saved-run-id>`.

With review enabled, submit a question that receives a 202 response. Confirm its
unpublished draft appears in **Human review** but not **Recorded execution**.
Refresh the page and reopen it from the pending list. Try a revision with feedback,
then approve and confirm the saved report and recorded workflow appear. A rejection
should leave no published report for that draft.
