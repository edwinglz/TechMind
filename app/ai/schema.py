"""The shape of a diagnostic brief, validated with Pydantic.

Both the mock and the live (Claude) brief must produce exactly this shape, so
the pages never have to care where a brief came from. After validation,
app/services/brief.py adds computed fields (costs, part names) that the AI is
never trusted to calculate.
"""

from typing import Literal

from pydantic import BaseModel, Field


class Source(BaseModel):
    type: Literal["manual", "past_ticket", "known_issue", "asset_history"]
    ref: str


class Cause(BaseModel):
    issue_id: str | None = None  # the company's known-issue ref, or None for a cause outside the known list
    cause: str
    likelihood: Literal["high", "medium", "low"]
    evidence: str
    sources: list[Source] = Field(default_factory=list)
    confirm_steps: list[str] = Field(default_factory=list)
    fix_steps: list[str] = Field(default_factory=list)
    part_ids: list[str] = Field(default_factory=list)
    estimated_minutes: int = 30


class SelfFix(BaseModel):
    applicable: bool = False
    steps: list[str] = Field(default_factory=list)
    risk_note: str = ""
    targets: list[str] = Field(default_factory=list)  # issue refs this self-fix would resolve


class Question(BaseModel):
    question: str
    why: str
    rules_in_or_out: list[str] = Field(default_factory=list)  # cause names


class BriefData(BaseModel):
    summary: str
    symptom_interpretation: str
    image_findings: list[str] = Field(default_factory=list)
    probable_causes: list[Cause]
    reporter_self_fix: SelfFix = Field(default_factory=SelfFix)
    questions_for_reporter: list[Question] = Field(default_factory=list)
    safety_warnings: list[str] = Field(default_factory=list)
    missing_info: list[str] = Field(default_factory=list)
