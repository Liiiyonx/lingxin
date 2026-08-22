"""Risk-decision orchestration built with LangGraph."""

from langgraph.graph import StateGraph, END

from core.database import RISK_ORDER, db_manager as db
from .state import RiskDecisionState


def fetch_current_node(state):
    student = db.get_student_by_id(state["student_id"]) or {}
    return {"current_risk": student.get("risk_level") or "low"}


def merge_risk_node(state):
    current = state.get("current_risk") or "low"
    evidence = state.get("risk_level") or "low"
    merged = current if RISK_ORDER.get(current, 0) >= RISK_ORDER.get(evidence, 0) else evidence
    return {"merged_risk": merged}


def write_state_node(state):
    db.update_student_state_from_evidence(
        student_id=state["student_id"],
        risk_level=state.get("risk_level") or "low",
        emotion_status=state.get("emotion_status") or "",
        source=state.get("source") or "unknown",
        counselor_id=state.get("counselor_id"),
        description=state.get("description") or "",
    )
    return {}


def build_risk_decision_graph():
    graph = StateGraph(RiskDecisionState)
    graph.add_node("fetch_current", fetch_current_node)
    graph.add_node("merge_risk", merge_risk_node)
    graph.add_node("write_state", write_state_node)
    graph.set_entry_point("fetch_current")
    graph.add_edge("fetch_current", "merge_risk")
    graph.add_edge("merge_risk", "write_state")
    graph.add_edge("write_state", END)
    return graph.compile()


def run_risk_decision(student_id, risk_level, emotion_status, source,
                      description="", counselor_id=None):
    """Run the risk-decision LangGraph workflow."""
    return build_risk_decision_graph().invoke({
        "student_id": student_id,
        "risk_level": risk_level or "low",
        "emotion_status": emotion_status or "",
        "source": source or "unknown",
        "description": description or "",
        "counselor_id": counselor_id,
        "current_risk": "low",
        "merged_risk": "low",
    })
