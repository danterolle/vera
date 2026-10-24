NODE_DETAILS = {
    "__start__": (
        "Input", "Validated LangGraph entry point.",
        "AnalysisRequest", "Initialized workflow state",
    ),
    "initialize": (
        "Control", "Detect events, calculate statistics, and recall memory.",
        "Query and normalized events", "Alerts, statistics, and recalled memories",
    ),
    "route": (
        "Control", "Select the minimum sufficient compositional resource plan.",
        "Initialized state", "ResourcePlan and derived compatibility route",
    ),
    "cag": (
        "Context", "Load stable curated cybersecurity knowledge.",
        "Conceptual query", "Curated evidence and memory",
    ),
    "rag": (
        "Context", "Combine curated knowledge with local corpus and optional Kuzu retrieval.",
        "Research query", "Curated knowledge, retrieved evidence, and memory",
    ),
    "tools": (
        "Context", "Combine CAG and RAG with exact CVE API lookups when live sources are enabled.",
        "Query containing CVE identifiers", "CAG, RAG, and API evidence or explicit unavailability",
    ),
    "stream": (
        "Context", "Combine curated knowledge with statistics from normalized events.",
        "Normalized events without requested retrieval", "Curated knowledge and stream evidence",
    ),
    "full": (
        "Context", "Combine CAG, RAG, and events; add CVE API lookups when needed and enabled.",
        "Mixed request or triggered alerts", "Correlated evidence from selected resources",
    ),
    "react_decide": (
        "Reasoning", "Choose a bounded evidence action or finish.",
        "Request, available evidence, and allowed CVE IDs", "Validated action decision",
    ),
    "react_execute": (
        "Context", "Execute an authorized local search or exact CVE lookup.",
        "Validated action and remaining tool budget", "Updated evidence and observations",
    ),
    "generate": (
        "Reasoning", "Produce a schema-constrained evidence-based draft.",
        "Selected evidence and validation feedback", "GeneratedAnswer with typed claims",
    ),
    "validate": (
        "Guardrail", "Validate citations and permit at most one bounded retry.",
        "Generated claims and evidence registry", "Validated or repaired claims",
    ),
    "reflection": (
        "Guardrail", "Score completeness and record evidence gaps.",
        "Validated claims and source status", "Structured reflection report",
    ),
    "review_assess": (
        "Guardrail", "Select only uncertain or high-risk drafts for human review.",
        "Draft, alerts, evidence, and reflection", "Review reasons or automatic continuation",
    ),
    "review_wait": (
        "Control", "Interrupt and await a local review decision on a durable checkpoint.",
        "Pending draft and review reasons", "Approve, reject, or request revision",
    ),
    "revise": (
        "Reasoning", "Regenerate with reviewer feedback before validation and another review.",
        "Original evidence and reviewer feedback", "Revised draft or explicit revision error",
    ),
    "finalize": (
        "Persistence", "Render, measure, and persist the completed analysis.",
        "Draft, incident, reflection, and trace", "Persistent AnalysisResult",
    ),
    "__end__": (
        "Output", "Return the typed analysis result.",
        "Finalized graph state", "API or CLI response",
    ),
}

POSITIONS = {
    "__start__": (600, 58),
    "initialize": (600, 140),
    "route": (600, 222),
    "cag": (120, 354),
    "rag": (360, 354),
    "tools": (600, 354),
    "stream": (840, 354),
    "full": (1080, 354),
    "react_decide": (340, 488),
    "react_execute": (860, 488),
    "generate": (600, 488),
    "validate": (600, 572),
    "reflection": (600, 656),
    "review_assess": (600, 735),
    "review_wait": (900, 805),
    "revise": (1080, 885),
    "finalize": (600, 850),
    "__end__": (600, 940),
}

NODE_LABELS = {
    "__start__": "START",
    "initialize": "Normalize input",
    "route": "Meta-controller",
    "cag": "CAG",
    "rag": "CAG + RAG",
    "tools": "CAG + RAG + API",
    "stream": "CAG + Stream",
    "full": "CAG + RAG + Stream",
    "react_decide": "Choose action",
    "react_execute": "Observe result",
    "generate": "Generate answer",
    "validate": "Validate claims",
    "reflection": "Reflect",
    "review_assess": "Check review risk",
    "review_wait": "Human review",
    "revise": "Revise answer",
    "finalize": "Persist result",
    "__end__": "END",
}
