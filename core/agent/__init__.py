"""LangGraph agent package for LingXin.

This package adds an orchestration layer on top of the existing digital-human
reply engine and student-risk writeback code.  The original call sites keep
owning persistence and realtime delivery; the agents only coordinate the
decision flow.
"""

from .digital_human_agent import run_digital_human
from .risk_decision_agent import run_risk_decision

__all__ = ["run_digital_human", "run_risk_decision"]
