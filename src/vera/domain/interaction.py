from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

InteractionIntent = Literal["social", "cybersecurity", "out_of_scope", "clarification"]


class InteractionPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    resolved_query: str = Field(min_length=1, max_length=1000)
    subject: str = Field(max_length=160)
    search_query: str = Field(max_length=300)
    intent: InteractionIntent
    needs_current: bool


class InteractionAssessment(BaseModel):
    model_config = ConfigDict(extra="forbid")

    subject: str = Field(max_length=160)
    needs_clarification: bool
    about_assistant: bool
    requires_subject_matter: bool
    concerns_cybersecurity: bool
    resolved_query: str = Field(min_length=1, max_length=1000)
    search_query: str = Field(max_length=300)
    needs_current: bool

    def to_plan(self) -> InteractionPlan:
        intent: InteractionIntent
        if self.about_assistant and not self.requires_subject_matter:
            intent = "social"
        elif self.needs_clarification:
            intent = "clarification"
        elif self.requires_subject_matter:
            intent = "cybersecurity" if self.concerns_cybersecurity else "out_of_scope"
        else:
            intent = "social"
        return InteractionPlan(
            intent=intent, resolved_query=self.resolved_query, subject=self.subject,
            search_query=self.search_query, needs_current=self.needs_current,
        )
