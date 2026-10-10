```mermaid
    graph TD

    A[Natural Language Query] --> B(Input Validation)
    B --> G(Initialize typed GraphState)
    C[(SQLite Memory)] --> G
    D[PCAP or Event Stream] --> E(tshark Parsing Event Normalization)
    E --> F(Deterministic Signal Detection)
    F --> G

    G --> H{Meta Controller}
    H --> |CVE Query| I(CAG_RAG_TOOL)
    H --> |Traffic Query| J(STREAM)
    H --> |Research Query| K(CAG_RAG)
    H --> |Conceptual Query| L(CAG_ONLY)
    H --> |Attack Detection| M(FULL)

    I --> N(Context and Evidence Assembly)
    J --> N(Context and Evidence Assembly)
    K --> N(Context and Evidence Assembly)
    L --> N(Context and Evidence Assembly)
    M --> N(Context and Evidence Assembly)

    N --> O(Structured generated answer or incident report)
    O --> P{Do all factual claims have valid sources?}

    P --> |Yes|Q(Reflection diagnostic assessment)
    P --> |No|R(Mark as inference, unknown or mock)

    R --> Q
    Q --> S(Memory and Trace Update)
    S --> T(Final Output\n Report, sources and execution trace)
