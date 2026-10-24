from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class InteractionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    intent: Literal["social", "cybersecurity", "out_of_scope", "clarification"]
    resolved_query: str = Field(min_length=1, max_length=1000)
    subject: str = Field(max_length=160)
    search_query: str = Field(max_length=300)
    needs_current: bool
