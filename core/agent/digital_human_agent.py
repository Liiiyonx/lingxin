"""Digital-human reply orchestration built with LangGraph."""

from langgraph.graph import StateGraph, END

from core.database import db_manager as db
from core.digital_human import _detect_crisis_level, generate_reply_result
from .state import DigitalHumanState


class DigitalHumanRunResult:
    """Result wrapper that keeps compatibility with ReplyResult call sites."""

    def __init__(self, content, crisis, crisis_level, emotion,
                 triggered_keywords, alert_created):
        self.content = content
        self.crisis = bool(crisis)
        self.crisis_level = int(crisis_level or 0)
        self.emotion = emotion or "neutral"
        self.triggered_keywords = list(triggered_keywords or [])
        self.alert_created = bool(alert_created)

    def to_dict(self):
        return {
            "reply": self.content,
            "crisis": self.crisis,
            "crisis_level": self.crisis_level,
            "emotion": self.emotion,
            "triggered_keywords": self.triggered_keywords,
            "alert_created": self.alert_created,
        }

    def __getitem__(self, key):
        return self.to_dict()[key]

    def get(self, key, default=None):
        return self.to_dict().get(key, default)


def _reply_result_for(state):
    settings = state.get("settings") or {}
    return generate_reply_result(
        state.get("message") or "",
        settings,
        state.get("student_name") or "",
        history=state.get("history") or [],
        student_context=state.get("student_context") or {},
    )


def _merge_keywords(*groups):
    seen = []
    for group in groups:
        for keyword in group or []:
            if keyword and keyword not in seen:
                seen.append(keyword)
    return seen


def detect_crisis_node(state):
    level, keywords = _detect_crisis_level(
        state.get("message") or "",
        state.get("settings") or {},
    )
    return {
        "crisis": level >= 2,
        "crisis_level": level,
        "triggered_keywords": list(keywords or []),
    }


def generate_reply_node(state):
    result = _reply_result_for(state)
    return {
        "reply": result.content,
        "crisis": bool(state.get("crisis") or result.crisis),
        "crisis_level": max(
            int(state.get("crisis_level") or 0),
            int(result.crisis_level or 0),
        ),
        "emotion": result.emotion,
        "triggered_keywords": _merge_keywords(
            state.get("triggered_keywords"),
            result.triggered_keywords,
        ),
    }


def alert_node(state):
    """Enter the crisis branch and optionally persist a high-risk alert."""
    reply = state.get("reply") or ""
    crisis_level = int(state.get("crisis_level") or 2)
    emotion = state.get("emotion") or "concerned"
    triggered_keywords = state.get("triggered_keywords") or []

    if not reply:
        result = _reply_result_for(state)
        reply = result.content
        crisis_level = max(crisis_level, int(result.crisis_level or 0))
        emotion = result.emotion
        triggered_keywords = _merge_keywords(
            triggered_keywords, result.triggered_keywords
        )

    alert_created = False
    if state.get("create_alert"):
        description = "数字人对话识别到危机信号：{}".format(
            (state.get("message") or "")[:200]
        )
        alert_id = db.create_alert(
            student_name=state.get("student_name") or "同学",
            student_class=state.get("student_class") or "",
            risk_level="high",
            emotion_type="危机",
            intensity=10,
            description=description,
            assigned_to=state.get("counselor_id"),
            student_id=state.get("student_id"),
        )
        alert_created = bool(alert_id)

    return {
        "reply": reply,
        "crisis": True,
        "crisis_level": crisis_level,
        "emotion": emotion,
        "triggered_keywords": triggered_keywords,
        "alert_created": alert_created,
    }


def build_digital_human_graph():
    graph = StateGraph(DigitalHumanState)
    graph.add_node("detect_crisis", detect_crisis_node)
    graph.add_node("generate_reply", generate_reply_node)
    graph.add_node("alert", alert_node)
    graph.set_entry_point("detect_crisis")
    graph.add_conditional_edges(
        "detect_crisis",
        lambda state: "alert" if state.get("crisis") else "generate_reply",
        {"alert": "alert", "generate_reply": "generate_reply"},
    )
    graph.add_edge("generate_reply", END)
    graph.add_edge("alert", END)
    return graph.compile()


def run_digital_human(message, student_name, settings, history=None,
                      student_context=None, create_alert=False,
                      student_id=None, counselor_id=None, student_class=""):
    """Run the digital-human LangGraph workflow."""
    final_state = build_digital_human_graph().invoke({
        "message": message or "",
        "student_name": student_name or "",
        "settings": settings or {},
        "history": history or [],
        "student_context": student_context or {},
        "create_alert": bool(create_alert),
        "student_id": student_id,
        "counselor_id": counselor_id,
        "student_class": student_class or "",
        "crisis": False,
        "reply": "",
        "crisis_level": 0,
        "emotion": "neutral",
        "triggered_keywords": [],
        "alert_created": False,
    })
    return DigitalHumanRunResult(
        content=final_state.get("reply") or "",
        crisis=final_state.get("crisis", False),
        crisis_level=final_state.get("crisis_level", 0),
        emotion=final_state.get("emotion", "neutral"),
        triggered_keywords=final_state.get("triggered_keywords", []),
        alert_created=final_state.get("alert_created", False),
    )
