from datetime import UTC, datetime

from pydantic import BaseModel, Field

from vera.domain.enums import Route


class GraphNode(BaseModel):
    id: str
    label: str
    category: str
    description: str
    input_contract: str
    output_contract: str
    x: int
    y: int
    active: bool = False
    executions: int = Field(default=0, ge=0)


class GraphEdge(BaseModel):
    source: str
    target: str
    label: str = ""
    conditional: bool = False
    active: bool = False


class GraphRun(BaseModel):
    run_id: str
    route: Route
    created_at: datetime


class GraphExecution(BaseModel):
    route: Route
    latency_ms: float = Field(ge=0)
    model_calls: int = Field(ge=0)
    tool_calls: int = Field(ge=0)
    evidence_documents: int = Field(ge=0)
    source_count: int = Field(ge=0)
    completeness: float = Field(ge=0, le=1)
    warning_count: int = Field(ge=0)


class GraphTopology(BaseModel):
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    selected_run_id: str | None = None
    nodes: list[GraphNode]
    edges: list[GraphEdge]
    mermaid: str
    recent_runs: list[GraphRun]
    execution: GraphExecution | None = None
