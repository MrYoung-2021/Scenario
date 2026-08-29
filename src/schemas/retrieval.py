"""Shared contracts for tiered retrieval and reusable knowledge."""

from datetime import datetime, timezone
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


KnowledgeCategory = Literal[
    "environment",
    "formation",
    "weapon",
    "tactics_campaign",
    "tactics_tactical",
    "task",
    "expert",
    "feedback",
]

DepositionCategory = Literal[
    "environment",
    "formation",
    "weapon",
    "tactics_campaign",
    "tactics_tactical",
    "task",
]
DepositionMode = Literal["summarize", "direct"]


class RetrievalQuery(BaseModel):
    query: str = Field(min_length=1)
    category: KnowledgeCategory
    level: str | None = None
    domain: str | None = None
    side: Literal["red", "blue", "all"] | None = None
    scenario_type: str | None = None

    def metadata_filter(self) -> dict[str, Any]:
        values = self.model_dump(exclude={"query"}, exclude_none=True)
        if values.get("side") == "all":
            values.pop("side")
        return values


class RetrievedItem(BaseModel):
    content: str
    backend: Literal["standard", "lightrag"]
    category: KnowledgeCategory
    score: float | None = None
    source: str
    source_id: str
    verified: bool = False
    metadata: dict[str, Any] = Field(default_factory=dict)


class RetrievalResult(BaseModel):
    items: list[RetrievedItem] = Field(default_factory=list)
    used_fallback: bool = False
    fallback_reason: str | None = None
    fallback_scopes: list[str] = Field(default_factory=list)


class DepositionJob(BaseModel):
    """A bounded, non-blocking request to promote retrieved/generated knowledge."""

    query: str = Field(default="", max_length=12000)
    content: str = Field(min_length=1, max_length=30000)
    title: str = Field(default="", max_length=200)
    category: DepositionCategory
    side: Literal["red", "blue", "all"] = "all"
    scope: str = Field(min_length=1, max_length=120)
    source_id: str = Field(min_length=1, max_length=200)
    mode: DepositionMode = "summarize"
    source: str = Field(min_length=1, max_length=200)
    level: Literal["campaign", "tactical", "general"] = "general"
    domain: str = Field(default="general", max_length=120)
    scenario_type: str = Field(default="all", max_length=120)
    context_hash: str = Field(default="", max_length=128)
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))


class TacticRecommendationItem(BaseModel):
    id: str
    label: str
    content: str
    level: Literal["campaign", "tactical"]
    source: str
    score: float
    verified: bool


class TacticRecommendations(BaseModel):
    red_objectives: list[TacticRecommendationItem] = Field(default_factory=list)
    blue_objectives: list[TacticRecommendationItem] = Field(default_factory=list)
    campaign_tactics: list[TacticRecommendationItem] = Field(default_factory=list)
    tactical_tactics: list[TacticRecommendationItem] = Field(default_factory=list)
    cache_hit: bool = False


class StructuredKnowledgeEntry(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    title: str = Field(min_length=1, max_length=200)
    category: KnowledgeCategory
    level: Literal["campaign", "tactical", "general"] = "general"
    applicable_conditions: list[str] = Field(default_factory=list)
    principle: str = Field(min_length=1)
    constraints: list[str] = Field(default_factory=list)
    source: str = Field(min_length=1)
    domain: str = "general"
    side: Literal["red", "blue", "all"] = "all"
    scenario_type: str = "all"

    @field_validator("applicable_conditions", "constraints")
    @classmethod
    def remove_blank_values(cls, values: list[str]) -> list[str]:
        return [value.strip() for value in values if value.strip()]


class KnowledgeCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    kb_id: KnowledgeCategory
    content: str = Field(min_length=1, max_length=5000)
    level: str = "general"
    domain: str = "general"
    side: Literal["red", "blue", "all"] = "all"
    scenario_type: str = "all"
    source: str = "manual"
    source_id: str = ""
