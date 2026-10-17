from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from vera.domain.enums import ClaimStatus
from vera.domain.evidence import Evidence

EntityKind = Literal[
    "cve",
    "cwe",
    "capec",
    "technique",
    "tactic",
    "mitigation",
    "group",
    "software",
    "guidance",
    "concept",
]
ENDPOINTS = {
    "has_weakness": ({"cve"}, {"cwe"}),
    "mitigates": ({"mitigation"}, {"technique"}),
    "uses": ({"group", "software"}, {"technique", "software"}),
    "part_of": ({"technique"}, {"tactic"}),
    "subtechnique_of": ({"technique"}, {"technique"}),
    "child_of": ({"cwe"}, {"cwe"}),
    "exploits_weakness": ({"capec"}, {"cwe"}),
    "covers": ({"guidance"}, {"concept"}),
    "includes_weakness": ({"guidance"}, {"cwe"}),
}


class Entity(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(min_length=1, max_length=200)
    kind: EntityKind
    name: str = Field(min_length=1, max_length=300)
    aliases: list[str] = Field(default_factory=list, max_length=30)


class Relation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    subject: Entity
    object: Entity
    predicate: Literal[
        "has_weakness",
        "mitigates",
        "uses",
        "part_of",
        "subtechnique_of",
        "child_of",
        "exploits_weakness",
        "covers",
        "includes_weakness",
    ]
    status: ClaimStatus = ClaimStatus.SYSTEM_INFERENCE
    supporting_quote: str = Field(default="", max_length=4000)
    field_path: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def check_endpoints(self) -> "Relation":
        source, target = ENDPOINTS[self.predicate]
        if self.subject.kind not in source or self.object.kind not in target:
            raise ValueError("Unsupported graph relation endpoints")
        return self


class GraphStatus(BaseModel):
    path: str
    available: bool = False
    schema_version: int | None = None
    counts: dict[str, int] = Field(default_factory=dict)
    error: str | None = None


class GraphRetrieval(BaseModel):
    enabled: bool = True
    attempted: bool = False
    available: bool = False
    seed_ids: list[str] = Field(default_factory=list)
    entity_ids: list[str] = Field(default_factory=list)
    assertion_ids: list[str] = Field(default_factory=list)
    evidence_ids: list[str] = Field(default_factory=list)
    record_keys: list[str] = Field(default_factory=list)
    hops: int = 0
    evidence: list[Evidence] = Field(default_factory=list, exclude=True)
    error: str | None = None


class GraphView(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    truncated: bool = False
    status: GraphStatus
    selected_ids: list[str] = Field(default_factory=list)
    provenance: bool = False
