from typing import Literal

from pydantic import BaseModel, Field


class IntakeResult(BaseModel):
    intent: Literal["FAQ", "REQUEST", "INCIDENT"]
    category: Literal["ACCESS", "DEVICE", "NETWORK", "APPLICATION", "OUTAGE", "GENERAL"]
    scope: Literal["individual", "team", "organization", "unknown"] = "unknown"
    summary: str = Field(max_length=200)
    reason: str = Field(max_length=300)


class PriorityResult(BaseModel):
    level: Literal["P1", "P2", "P3"]
    explanation: str


class Evidence(BaseModel):
    segment_id: str
    source: str
    title: str
    excerpt: str
    score: float
    channels: list[str] = Field(default_factory=list)


class AnswerReview(BaseModel):
    approved: bool
    reason: str


class SupportInput(BaseModel):
    message: str = Field(min_length=1, max_length=4000)
    request_id: str = Field(min_length=1, max_length=100)
    thread_id: str | None = None


class SignInInput(BaseModel):
    username: str = Field(max_length=80)
    password: str = Field(max_length=200)


class WorkOrderUpdate(BaseModel):
    phase: Literal["INVESTIGATING", "RESOLVED"]
    note: str = Field(min_length=1, max_length=2000)
    expected_revision: int = Field(ge=0)
