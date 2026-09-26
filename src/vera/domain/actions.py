import re
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

CVE_ID = re.compile(r"CVE-\d{4}-\d{4,19}")


class ReActAction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    action: Literal["finish", "search_corpus", "lookup_cve"]
    query: str | None = Field(default=None, min_length=1, max_length=500)
    cve_id: str | None = None

    @model_validator(mode="after")
    def check_arguments(self) -> "ReActAction":
        if self.action == "finish" and (self.query is not None or self.cve_id is not None):
            raise ValueError("finish does not accept arguments")
        if self.action == "search_corpus" and (self.query is None or self.cve_id is not None):
            raise ValueError("search_corpus requires only a query")
        if self.action == "lookup_cve" and (
            self.query is not None
            or self.cve_id is None
            or CVE_ID.fullmatch(self.cve_id) is None
        ):
            raise ValueError("lookup_cve requires a valid CVE identifier")
        return self


class ReActObservation(BaseModel):
    action: ReActAction
    outcome: Literal["completed", "skipped", "rejected"]
    evidence_ids: list[str]
