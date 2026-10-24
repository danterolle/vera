from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from vera.domain.enums import Route


class ResourcePlan(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    use_cag: bool = True
    use_rag: bool = False
    use_tools: bool = False
    use_stream: bool = False
    cve_ids: list[str] = Field(default_factory=list)
    technique_ids: list[str] = Field(default_factory=list)
    web_query: str | None = Field(default=None, max_length=512)
    intent: Literal["social", "cybersecurity", "out_of_scope", "clarification"] = "cybersecurity"
    resolved_query: str | None = Field(default=None, max_length=1000)
    subject: str | None = Field(default=None, max_length=160)
    search_query: str | None = Field(default=None, max_length=300)
    reasons: list[str] = Field(default_factory=list)

    @field_validator("cve_ids", "technique_ids")
    @classmethod
    def unique_identifiers(cls, values: list[str]) -> list[str]:
        return sorted(set(values))

    @property
    def route(self) -> Route:
        if self.use_stream and (self.use_rag or self.use_tools):
            return Route.FULL
        if self.use_stream:
            return Route.STREAM
        if self.use_tools:
            return Route.CAG_RAG_TOOL
        if self.use_rag:
            return Route.CAG_RAG
        return Route.CAG_ONLY
