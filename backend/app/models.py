"""Keep tools, evidence references and answer modes explicit at the API boundary."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat

Route = Literal["assets", "timeseries", "docs", "report"]


class Asset(BaseModel):
    id: str
    name: str
    parent_id: str | None = None
    description: str = ""


class Point(BaseModel):
    timestamp: int = Field(ge=0)
    value: FiniteFloat


class Series(BaseModel):
    id: str
    name: str
    asset_id: str
    unit: str
    points: list[Point]


class Corpus(BaseModel):
    source: Literal["synthetic", "cdf_snapshot"]
    snapshot_at: str
    assets: list[Asset]
    series: list[Series]


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    question: str = Field(min_length=3, max_length=2000)
    asset_id: str
    timeseries_id: str | None = None
    start_ms: int | None = Field(default=None, ge=0)
    end_ms: int | None = Field(default=None, ge=0)
    mode: Literal["operator", "executive"] = "operator"


class Trace(BaseModel):
    agent: str
    tool: str
    detail: str
    evidence: list[str] = Field(default_factory=list)


class Answer(BaseModel):
    text: str
    citations: list[str]
    source: str
    route: Route
    trace: list[Trace]
    limitations: list[str]
