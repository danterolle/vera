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
        "Context", "Combine curated knowledge with hybrid local retrieval.",
        "Research query", "Ranked corpus evidence",
    ),
    "tools": (
        "Context", "Add exact read-only vulnerability source lookups.",
        "Query containing CVE identifiers", "CAG, RAG, and live API evidence",
    ),
    "stream": (
        "Context", "Build context from normalized event-stream evidence.",
        "Normalized events without alerts", "Statistics and stream evidence",
    ),
    "full": (
        "Context", "Combine stream, retrieval, and exact sources for composite requests.",
        "Mixed request or triggered alerts", "Correlated evidence from selected resources",
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
    "generate": (600, 488),
    "validate": (600, 572),
    "reflection": (600, 656),
    "finalize": (600, 740),
    "__end__": (600, 824),
}

NODE_LABELS = {
    "__start__": "START",
    "initialize": "Normalize input",
    "route": "Meta-controller",
    "cag": "CAG knowledge",
    "rag": "RAG retrieval",
    "tools": "Live CVE APIs",
    "stream": "Event analysis",
    "full": "Full analysis",
    "generate": "Generate answer",
    "validate": "Validate claims",
    "reflection": "Reflect",
    "finalize": "Persist result",
    "__end__": "END",
}
