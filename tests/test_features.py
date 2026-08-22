# -*- coding: utf-8 -*-
"""Feature-level regression tests for closed-loop behaviours.

These tests are intentionally focused on the integration seams that are easy
to break when new code is merged: digital-human crisis handling, alert state
machines, assessment risk writeback, appointment side effects, and counselor
data isolation.
"""
import os
import sys
import time
import unittest
import uuid
from datetime import datetime, timedelta

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

from app import create_app  # noqa: E402

APP = create_app()
APP.config["TESTING"] = True

from api.routes import db  # noqa: E402
from core.database import (  # noqa: E402
    AlertLog,
    Appointment,
    AssessmentResult,
    DigitalHumanLog,
    Message,
    Reminder,
    Student,
    StudentProfile,
    StudentRiskEvidence,
    Todo,
)
from core.digital_human import (  # noqa: E402
    _detect_crisis_level,
    _effective_settings,
    _engagement_hint,
    generate_reply,
    generate_reply_result,
)


class FeatureRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = APP.test_client()

        admin = cls.client.post(
            "/api/auth/login",
            json={"username": "admin", "password": "admin123"},
        ).get_json()["data"]["token"]
        zhangwei = cls.client.post(
            "/api/auth/login",
            json={"username": "zhangwei", "password": "counsel123"},
        ).get_json()["data"]["token"]
        liuqiang = cls.client.post(
            "/api/auth/login",
            json={"username": "liuqiang", "password": "counsel123"},
        ).get_json()["data"]["token"]

        cls.admin = {"Authorization": "Bearer " + admin}
        cls.zhangwei = {"Authorization": "Bearer " + zhangwei}
        cls.liuqiang = {"Authorization": "Bearer " + liuqiang}

        profile = cls.client.get(
            "/api/auth/profile", headers=cls.zhangwei
        ).get_json()["data"]
        cls.zhangwei_user_id = profile["user_id"]

    @staticmethod
    def _student_payload(suffix):
        suffix = suffix or uuid.uuid4().hex[:10]
        return {
            "student_id": "FEAT-" + suffix,
            "name": "Feature-" + suffix,
            "gender": "Unspecified",
            "college": "Regression",
            "class_name": "FeatureTest",
        }

    def _create_student(self, suffix=None, headers=None):
        headers = headers or self.admin
        suffix = suffix or uuid.uuid4().hex[:10]
        resp = self.client.post(
            "/api/student/add",
            json=self._student_payload(suffix),
            headers=headers,
        )
        self.assertEqual(resp.status_code, 201)
        return resp.get_json()["data"]["id"]

    def _login_student(self, student_no, student_id):
        db.set_student_password(student_id, "feature123")
        resp = self.client.post(
            "/api/student/login",
            json={"student_id": student_no, "password": "feature123"},
        )
        self.assertEqual(resp.status_code, 200)
        return resp.get_json()["data"]["token"]

    def _cleanup_student(self, student_id):
        with db.get_session() as session:
            for model in (
                DigitalHumanLog,
                Message,
                Todo,
                Appointment,
                StudentProfile,
                AssessmentResult,
                StudentRiskEvidence,
                AlertLog,
                Reminder,
            ):
                session.query(model).filter(model.student_id == student_id).delete(
                    synchronize_session=False
                )
            session.query(Student).filter(Student.id == student_id).delete(
                synchronize_session=False
            )

    def test_digital_human_crisis_reply_marks_crisis(self):
        content, crisis = generate_reply("我想死，活着没有意义")
        self.assertTrue(crisis)
        self.assertTrue(content)

    def test_digital_human_crisis_level_detects_variants(self):
        self.assertEqual(_detect_crisis_level("我想死，活着没有意义")[0], 3)
        self.assertEqual(_detect_crisis_level("我好累，不想坚持了")[0], 2)
        self.assertEqual(_detect_crisis_level("活着没意思，反正也没人在乎我")[0], 2)
        self.assertEqual(_detect_crisis_level("最近有点累")[0], 1)
        self.assertEqual(_detect_crisis_level("今天天气不错")[0], 0)

        result = generate_reply_result("我好累，不想坚持了")
        self.assertEqual(result.crisis_level, 2)
        self.assertTrue(result.crisis)
        self.assertEqual(result.emotion, "concerned")

    def test_digital_human_personalization_and_engagement_hint(self):
        adjusted = _effective_settings(
            {"style": "humor", "humor": 3},
            {"risk_level": "critical", "emotion_status": "绝望"},
        )
        self.assertEqual(adjusted["style"], "pro")
        self.assertEqual(adjusted["humor"], 1)

        hint = _engagement_hint([
            {"role": "assistant", "content": "先休息一下，好吗？"},
            {"role": "user", "content": "我还是很累"},
            {"role": "assistant", "content": "我们只做一小步。"},
            {"role": "user", "content": "好"},
        ])
        self.assertIn("开放问题", hint)

    def test_digital_human_crisis_log_and_alert_are_linked(self):
        student_id = self._create_student()
        try:
            msg_id = db.create_message(
                student_id=student_id,
                counselor_id=1,
                sender_type="student",
                sender_id=student_id,
                content="我想伤害自己",
            )
            log_id = db.create_digital_human_log(
                counselor_id=1,
                student_id=student_id,
                message_id=msg_id,
                content="我已经看到了，请先注意自己的安全。",
                crisis=True,
            )
            alert_id = db.create_alert(
                student_name="Feature",
                student_class="FeatureTest",
                risk_level="high",
                emotion_type="危机",
                intensity=10,
                description="数字人危机模拟",
                assigned_to=1,
                student_id=student_id,
            )

            alert = db.get_alert(alert_id)
            self.assertIsNotNone(alert)
            self.assertEqual(alert["emotion_type"], "危机")
            self.assertEqual(alert["student_id"], student_id)
            self.assertEqual(alert["status"], "pending")

            handled = db.mark_digital_human_log_handled(log_id, 1, "已电话确认")
            self.assertTrue(handled["handled"])
            self.assertEqual(handled["handled_by"], 1)
        finally:
            self._cleanup_student(student_id)

    def test_digital_human_log_records_crisis_level_and_summary(self):
        student_id = self._create_student()
        try:
            msg_id = db.create_message(
                student_id=student_id,
                counselor_id=1,
                sender_type="student",
                sender_id=student_id,
                content="最近考试压力很大，晚上也睡不好",
            )
            log_id = db.create_digital_human_log(
                counselor_id=1,
                student_id=student_id,
                message_id=msg_id,
                content="我们先一起把任务拆小，今晚早点休息。",
                crisis=True,
                crisis_level=2,
                triggered_keywords=["压力", "睡不好"],
            )
            logs = db.get_digital_human_logs(1, limit=10)
            matching = [log for log in logs if log["id"] == log_id]
            self.assertTrue(matching)
            self.assertEqual(matching[0]["crisis_level"], 2)
            self.assertEqual(matching[0]["triggered_keywords"], "压力,睡不好")

            time.sleep(0.02)
            db.create_message(
                student_id=student_id,
                counselor_id=1,
                sender_type="student",
                sender_id=student_id,
                content="老师，那我今晚先试试早点睡",
            )

            summary = db.get_digital_human_summary(1)
            student_summary = next(
                (item for item in summary if item["student_id"] == student_id),
                None,
            )
            self.assertIsNotNone(student_summary)
            self.assertEqual(student_summary["rounds"], 1)
            self.assertEqual(student_summary["high_risk_count"], 1)
            self.assertTrue(student_summary["follow_up"])
            self.assertEqual(student_summary["continued_after_ai"], 1)
            self.assertEqual(student_summary["engagement_rate"], 100)
        finally:
            self._cleanup_student(student_id)

    def test_alert_state_machine_and_resolution_recomputes_risk(self):
        student_id = self._create_student()
        try:
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="high",
                emotion_status="焦虑",
                source="feature_setup",
                counselor_id=1,
            )
            alert_id = db.create_alert(
                student_name="Feature",
                student_class="FeatureTest",
                risk_level="high",
                emotion_type="危机",
                description="state machine regression",
                assigned_to=1,
                student_id=student_id,
            )

            ack = self.client.put(
                f"/api/alert/{alert_id}/acknowledge", headers=self.admin
            )
            self.assertEqual(ack.status_code, 200)
            self.assertEqual(db.get_alert(alert_id)["status"], "acknowledged")

            duplicate = self.client.put(
                f"/api/alert/{alert_id}/acknowledge", headers=self.admin
            )
            self.assertEqual(duplicate.status_code, 400)

            resolved = self.client.put(
                f"/api/alert/{alert_id}/resolve",
                json={"resolution": "Feature regression resolved"},
                headers=self.admin,
            )
            self.assertEqual(resolved.status_code, 200)
            self.assertEqual(db.get_alert(alert_id)["status"], "resolved")

            detail = self.client.get(
                f"/api/student/{student_id}", headers=self.admin
            ).get_json()["data"]
            self.assertEqual(detail["risk_level"], "low")
        finally:
            self._cleanup_student(student_id)

    def test_assessment_item9_two_creates_high_risk_and_alert(self):
        suffix = uuid.uuid4().hex[:10]
        student_id = self._create_student(suffix)
        try:
            token = self._login_student("FEAT-" + suffix, student_id)
            headers = {"Authorization": "Bearer " + token}
            answers = [{"q": i + 1, "a": 0} for i in range(23)]
            answers[8]["a"] = 2

            resp = self.client.post(
                "/api/assessment/submit",
                json={"answers": answers, "duration_seconds": 30},
                headers=headers,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertTrue(resp.get_json()["data"]["crisis"])

            detail = self.client.get(
                f"/api/student/{student_id}", headers=self.admin
            ).get_json()["data"]
            self.assertEqual(detail["risk_level"], "high")

            with db.get_session() as session:
                alert_count = (
                    session.query(AlertLog)
                    .filter(AlertLog.student_id == student_id, AlertLog.emotion_type == "危机")
                    .count()
                )
            self.assertGreaterEqual(alert_count, 1)
        finally:
            self._cleanup_student(student_id)

    def test_assessment_phq10_without_item9_creates_medium_risk(self):
        suffix = uuid.uuid4().hex[:10]
        student_id = self._create_student(suffix)
        try:
            token = self._login_student("FEAT-" + suffix, student_id)
            headers = {"Authorization": "Bearer " + token}
            answers = [{"q": i + 1, "a": 0} for i in range(23)]
            for i in range(5):
                answers[i]["a"] = 2

            resp = self.client.post(
                "/api/assessment/submit",
                json={"answers": answers, "duration_seconds": 30},
                headers=headers,
            )
            self.assertEqual(resp.status_code, 200)
            self.assertFalse(resp.get_json()["data"]["crisis"])

            detail = self.client.get(
                f"/api/student/{student_id}", headers=self.admin
            ).get_json()["data"]
            self.assertEqual(detail["risk_level"], "medium")
        finally:
            self._cleanup_student(student_id)

    def test_appointment_confirmed_creates_todo_and_completed_creates_profile(self):
        student_id = self._create_student()
        try:
            appt_time = datetime.now() + timedelta(days=2)
            appt_id = db.create_appointment(
                student_id=student_id,
                counselor_id=1,
                appointment_time=appt_time,
                reason="回归测试预约",
                duration=30,
            )

            confirmed = self.client.put(
                f"/api/appointments/{appt_id}/status",
                json={"status": "confirmed"},
                headers=self.admin,
            )
            self.assertEqual(confirmed.status_code, 200)
            with db.get_session() as session:
                todo_count = session.query(Todo).filter(
                    Todo.student_id == student_id, Todo.category == "appointment"
                ).count()
            self.assertEqual(todo_count, 1)

            completed = self.client.put(
                f"/api/appointments/{appt_id}/status",
                json={"status": "completed", "notes": "已完成谈心"},
                headers=self.admin,
            )
            self.assertEqual(completed.status_code, 200)
            with db.get_session() as session:
                profile_count = session.query(StudentProfile).filter(
                    StudentProfile.student_id == student_id,
                    StudentProfile.record_type == "appointment_completed",
                ).count()
            self.assertEqual(profile_count, 1)
        finally:
            self._cleanup_student(student_id)

    def test_counselor_student_list_is_isolated_by_owner(self):
        suffix_a = uuid.uuid4().hex[:10]
        suffix_b = uuid.uuid4().hex[:10]
        student_a = self._create_student(suffix_a, headers=self.zhangwei)
        student_b = self._create_student(suffix_b, headers=self.liuqiang)
        try:
            zhang_list = self.client.get(
                "/api/student/list?per_page=100", headers=self.zhangwei
            ).get_json()["data"]
            liu_list = self.client.get(
                "/api/student/list?per_page=100", headers=self.liuqiang
            ).get_json()["data"]

            zhang_ids = {item["id"] for item in zhang_list}
            liu_ids = {item["id"] for item in liu_list}

            self.assertIn(student_a, zhang_ids)
            self.assertNotIn(student_b, zhang_ids)
            self.assertIn(student_b, liu_ids)
            self.assertNotIn(student_a, liu_ids)
        finally:
            self._cleanup_student(student_a)
            self._cleanup_student(student_b)

    def test_manual_risk_downgrade_is_audited(self):
        student_id = self._create_student()
        try:
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="high",
                emotion_status="恐惧",
                source="video_call_summary",
                counselor_id=1,
            )
            resp = self.client.put(
                f"/api/student/{student_id}/risk",
                json={"risk_level": "medium", "reason": "Regression manual review"},
                headers=self.admin,
            )
            self.assertEqual(resp.status_code, 200)
            timeline = self.client.get(
                f"/api/student/{student_id}/risk-timeline", headers=self.admin
            ).get_json()["data"]
            sources = {item["source"] for item in timeline}
            self.assertIn("manual", sources)
        finally:
            self._cleanup_student(student_id)

    def test_completed_student_care_todo_writes_followup_evidence(self):
        student_id = self._create_student()
        try:
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="high",
                emotion_status="压抑",
                source="feature_setup",
                counselor_id=1,
            )
            todo_id = db.create_todo(
                user_id=1,
                title="回归学生跟进",
                category="student_care",
                student_id=student_id,
            )
            resp = self.client.put(
                f"/api/workplan/todo/{todo_id}/complete", headers=self.admin
            )
            self.assertEqual(resp.status_code, 200)
            timeline = self.client.get(
                f"/api/student/{student_id}/risk-timeline", headers=self.admin
            ).get_json()["data"]
            sources = {item["source"] for item in timeline}
            self.assertIn("todo_done", sources)
        finally:
            self._cleanup_student(student_id)

    def test_workplan_today_and_todo_student_relationship(self):
        student_id = self._create_student(headers=self.zhangwei)
        try:
            todo_id = db.create_todo(
                user_id=self.zhangwei_user_id,
                title="带学生关系的待办回归",
                category="student_care",
                student_id=student_id,
            )

            resp = self.client.get(
                "/api/workplan/today", headers=self.zhangwei
            )
            self.assertEqual(resp.status_code, 200)
            self.assertGreater(
                resp.get_json()["data"]["student_summary"]["total"], 0
            )

            workplan = db.get_today_workplan(counselor_id=self.zhangwei_user_id)
            matching = [
                item for item in workplan["todo_list"]
                if item["id"] == f"todo_{todo_id}"
            ]
            self.assertTrue(matching)
            self.assertEqual(matching[0]["student_db_id"], student_id)
        finally:
            self._cleanup_student(student_id)

    def test_crisis_center_assign_and_close_flow(self):
        student_id = self._create_student()
        try:
            db.update_student_state_from_evidence(
                student_id=student_id,
                risk_level="high",
                emotion_status="自伤风险",
                source="assessment",
                counselor_id=1,
            )
            alert_id = db.create_alert(
                student_name="Feature",
                student_class="FeatureTest",
                risk_level="high",
                emotion_type="危机",
                description="crisis center regression",
                assigned_to=1,
                student_id=student_id,
            )

            assign = self.client.put(
                f"/api/alert/crisis-center/{alert_id}/assign",
                json={"assigned_to": 2, "note": "转介心理中心"},
                headers=self.admin,
            )
            self.assertEqual(assign.status_code, 200)
            self.assertEqual(db.get_alert(alert_id)["assigned_to"], 2)
            self.assertTrue(db.get_alert(alert_id)["escalated"])

            close = self.client.put(
                f"/api/alert/crisis-center/{alert_id}/close",
                json={"resolution": "危机处置完成"},
                headers=self.admin,
            )
            self.assertEqual(close.status_code, 200)
            self.assertEqual(db.get_alert(alert_id)["status"], "resolved")
        finally:
            self._cleanup_student(student_id)


if __name__ == "__main__":
    unittest.main(verbosity=2)
