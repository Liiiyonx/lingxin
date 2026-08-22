"""Shared LangGraph state definitions."""

from typing import Optional, TypedDict


class DigitalHumanState(TypedDict, total=False):
    message: str
    student_name: str
    settings: dict
    history: list
    student_context: dict
    create_alert: bool
    student_id: Optional[int]
    counselor_id: Optional[int]
    student_class: str
    crisis: bool
    reply: str
    crisis_level: int
    emotion: str
    triggered_keywords: list
    alert_created: bool


class RiskDecisionState(TypedDict, total=False):
    student_id: int
    risk_level: str
    emotion_status: str
    source: str
    description: str
    counselor_id: Optional[int]
    current_risk: str
    merged_risk: str
