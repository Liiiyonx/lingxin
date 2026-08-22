"""LangGraph agent workflow tests."""

import os
import sys
import unittest
import uuid

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from app import create_app  # noqa: E402

APP = create_app()
APP.config["TESTING"] = True

from api.routes import db  # noqa: E402
from core.agent import run_digital_human, run_risk_decision  # noqa: E402
from core.database import (  # noqa: E402
    AlertLog,
    Reminder,
    Student,
    StudentRiskEvidence,
)


class AgentWorkflowTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = APP.test_client()

    def _create_student(self):
        suffix = uuid.uuid4().hex[:10]
        student_id = db.create_student(
            student_id="AGENT-" + suffix,
            name="Agent-" + suffix,
            gender="Unspecified",
            college="Regression",
            class_name="AgentTest",
        )
        return student_id, "Agent-" + suffix

    def _cleanup_student(self, student_id):
        with db.get_session() as session:
            for model in (
                StudentRiskEvidence,
                Reminder,
                AlertLog,
            ):
                session.query(model).filter(model.student_id == student_id).delete(
                    synchronize_session=False
                )
            session.query(Student).filter(Student.id == student_id).delete(
                synchronize_session=False
            )

    def test_digital_human_crisis_workflow(self):
        result = run_digital_human(
            "我想死，活着没有意义",
            "同学",
            {"enabled": True, "name": "小聆", "humor": 3, "style": "humor"},
        )
        self.assertTrue(result.crisis)
        self.assertGreaterEqual(result.crisis_level, 2)
        self.assertTrue(result["reply"])
        self.assertFalse(result.alert_created)

    def test_digital_human_crisis_workflow_can_create_alert(self):
        student_id, student_name = self._create_student()
        try:
            result = run_digital_human(
                "我想死，活着没有意义",
                student_name,
                {"enabled": True, "name": "小聆", "humor": 3, "style": "humor"},
                create_alert=True,
                student_id=student_id,
                counselor_id=1,
                student_class="AgentTest",
            )
            self.assertTrue(result.crisis)
            self.assertTrue(result.alert_created)
            with db.get_session() as session:
                count = (
                    session.query(AlertLog)
                    .filter(
                        AlertLog.student_id == student_id,
                        AlertLog.emotion_type == "危机",
                    )
                    .count()
                )
            self.assertGreaterEqual(count, 1)
        finally:
            self._cleanup_student(student_id)

    def test_digital_human_normal_workflow(self):
        result = run_digital_human(
            "考试压力大",
            "同学",
            {"enabled": True, "name": "小聆", "humor": 3, "style": "humor"},
        )
        self.assertFalse(result.crisis)
        self.assertTrue(result.content)

    def test_risk_decision_keeps_highest_risk(self):
        student_id, _ = self._create_student()
        try:
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="high",
                emotion_status="焦虑",
                source="assessment",
                counselor_id=1,
            )
            result = run_risk_decision(
                student_id=student_id,
                risk_level="medium",
                emotion_status="低落",
                source="talk_report",
                description="agent regression",
                counselor_id=1,
            )
            self.assertEqual(result["merged_risk"], "high")
            self.assertEqual(db.get_student_by_id(student_id)["risk_level"], "high")
        finally:
            self._cleanup_student(student_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
