# -*- coding: utf-8 -*-
"""Closed-loop regression test for student risk evidence and resolution.

The assessment/talk-report evidence paths are written through DatabaseManager
because those API endpoints require a student session and external scoring.
The rest of the loop (auth, student creation, manual downgrade, alert
resolution, risk timeline) goes through Flask test_client.
"""
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
from core.database import Student, StudentRiskEvidence, Reminder, AlertLog  # noqa: E402


class ClosedLoopTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = APP.test_client()
        resp = cls.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        )
        data = resp.get_json()
        cls.token = data["data"]["token"]
        cls.headers = {"Authorization": "Bearer " + cls.token}

    def _create_student(self):
        suffix = uuid.uuid4().hex[:10]
        student_no = "LOOP-" + suffix
        resp = self.client.post(
            "/api/student/add",
            json={
                "student_id": student_no,
                "name": "ClosedLoop-" + suffix,
                "gender": "Unspecified",
                "college": "Regression",
                "class_name": "ClosedLoop",
            },
            headers=self.headers,
        )
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["data"]["id"]

    def _cleanup_student(self, student_id):
        with db.get_session() as session:
            session.query(StudentRiskEvidence).filter(
                StudentRiskEvidence.student_id == student_id
            ).delete(synchronize_session=False)
            session.query(Reminder).filter(
                Reminder.student_id == student_id
            ).delete(synchronize_session=False)
            session.query(AlertLog).filter(
                AlertLog.student_id == student_id
            ).delete(synchronize_session=False)
            session.query(Student).filter(
                Student.id == student_id
            ).delete(synchronize_session=False)

    def test_risk_merge_explicit_downgrade_and_resolution(self):
        student_id = self._create_student()
        try:
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="high",
                emotion_status="焦虑",
                source="assessment",
                counselor_id=1,
                description="PHQ-9 high evidence",
            )
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="medium",
                emotion_status="低落",
                source="talk_report",
                counselor_id=1,
                description="Talk report medium evidence",
            )

            detail = self.client.get(
                "/api/student/" + str(student_id), headers=self.headers
            ).get_json()["data"]
            self.assertEqual(detail["risk_level"], "high")

            timeline = self.client.get(
                "/api/student/" + str(student_id) + "/risk-timeline",
                headers=self.headers,
            ).get_json()["data"]
            sources = {item["source"] for item in timeline}
            self.assertIn("assessment", sources)
            self.assertIn("talk_report", sources)

            # General student updates must not silently overwrite risk state
            # and bypass the evidence timeline.
            bypass = self.client.put(
                "/api/student/" + str(student_id),
                json={"risk_level": "low", "emotion_status": "正常"},
                headers=self.headers,
            )
            self.assertEqual(bypass.status_code, 400)

            # Explicit manual downgrade is the only non-resolution channel that
            # may lower a conservative high-risk state.
            resp = self.client.put(
                "/api/student/" + str(student_id) + "/risk",
                json={"risk_level": "medium", "reason": "Regression manual downgrade"},
                headers=self.headers,
            )
            self.assertEqual(resp.status_code, 200)
            detail = self.client.get(
                "/api/student/" + str(student_id), headers=self.headers
            ).get_json()["data"]
            self.assertEqual(detail["risk_level"], "medium")

            # Raise again, then close an alert and verify the student leaves the
            # high-risk list through the resolution recomputation path.
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="high",
                emotion_status="恐惧",
                source="video_call_summary",
                counselor_id=1,
                description="Video summary high evidence",
            )
            alert_id = db.create_alert(
                student_name="ClosedLoop",
                student_class="ClosedLoop",
                risk_level="high",
                emotion_type="危机",
                description="Closed-loop regression alert",
                student_id=student_id,
                assigned_to=1,
            )
            resp = self.client.put(
                "/api/alert/" + str(alert_id) + "/resolve",
                json={"resolution": "Regression resolution"},
                headers=self.headers,
            )
            self.assertEqual(resp.status_code, 200)

            detail = self.client.get(
                "/api/student/" + str(student_id), headers=self.headers
            ).get_json()["data"]
            self.assertEqual(detail["risk_level"], "low")

            timeline = self.client.get(
                "/api/student/" + str(student_id) + "/risk-timeline",
                headers=self.headers,
            ).get_json()["data"]
            sources = {item["source"] for item in timeline}
            self.assertIn("manual", sources)
            self.assertIn("alert_resolution", sources)
        finally:
            self._cleanup_student(student_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
