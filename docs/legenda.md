```mermaid
    graph LR

    direction TB
    L1[CAG_RAG_TOOL = RAG + API lookups]
    L2[STREAM = CAG + structured events]
    L3[CAG_RAG = CAG + local retrieval]
    L4[CAG_ONLY = stable knowledge]
    L5[FULL = CAG + RAG + stream + tools]

