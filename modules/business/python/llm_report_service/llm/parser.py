from __future__ import annotations

from typing import Any, Dict, List, Literal

from pydantic import BaseModel, Field


class ReportOutput(BaseModel):
    event_type: str = Field(...)
    summary: str = Field(...)
    risk_level: Literal["low", "medium", "high"] = Field(...)
    key_observations: List[str] = Field(default_factory=list)
    confidence: float = Field(...)


def normalize_report(d: Dict[str, Any]) -> Dict[str, Any]:
    obj = ReportOutput.model_validate(d)
    return obj.model_dump()
