# -*- coding: utf-8 -*-
"""
聆心 — API 全接口冒烟测试
=========================
使用 Flask test_client 逐一请求所有路由，断言「不因方法缺失/字段不对齐而 500」。

设计原则：
- 只依赖标准库 unittest，零额外依赖，`python tests/test_routes.py` 直接运行。
- 对需要外部 LLM/模型/文件上传的接口，测试其「入参校验」路径（返回 400/403），
  以此证明路由在调用外部服务之前已正确接线（不会再出现 AttributeError）。
- 对读接口断言 200；对写接口接受 200/201/400/404 等合法状态。

运行：  python tests/test_routes.py
       （也可用 pytest tests/ -q）
"""
import os
import sys
import unittest

ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT_DIR)

# 注意：不要在此处手动设置 DASHSCOPE_API_KEY。
# app/config 内部的 load_dotenv() 会从 .env 读取密钥，且不会覆盖已存在的环境变量；
# 若提前 setdefault 成空串，会导致 RAG 引擎因「无 key」而跳过初始化。
from app import create_app  # noqa: E402


class RouteSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = create_app()
        cls.app.config["TESTING"] = True
        cls.client = cls.app.test_client()
        # 登录管理员，拿到 token
        resp = cls.client.post("/api/auth/login",
                               json={"username": "admin", "password": "admin123"})
        data = resp.get_json()
        cls.token = data["data"]["token"]
        cls.h = {"Authorization": "Bearer " + cls.token}

    def req(self, method, path, expect, json=None, headers=None):
        """通用请求断言：状态码必须落在 expect 集合内。"""
        h = headers or self.h
        if json is not None:
            r = getattr(self.client, method)(path, json=json, headers=h)
        else:
            r = getattr(self.client, method)(path, headers=h)
        self.assertIn(
            r.status_code, expect,
            f"{method.upper()} {path} -> {r.status_code} (期望 {expect}); body={r.get_data(as_text=True)[:300]}"
        )
        return r

    # ---------- 鉴权 ----------
    def test_01_login_required(self):
        r = self.client.get("/api/alert/list")
        self.assertEqual(r.status_code, 401, "未带 token 应返回 401")

    def test_02_login_success(self):
        self.assertTrue(self.token)

    def test_03_logout(self):
        # 用独立 token 测试注销，避免影响共享 token
        tok = self.client.post("/api/auth/login",
                               json={"username": "admin", "password": "admin123"}).get_json()["data"]["token"]
        r = self.client.post("/api/auth/logout", headers={"Authorization": "Bearer " + tok})
        self.assertIn(r.status_code, {200, 400})

    # ---------- 个人资料 ----------
    def test_04_profile_get(self):
        self.req("get", "/api/auth/profile", {200})

    def test_05_profile_put(self):
        self.req("put", "/api/auth/profile", {200, 400},
                 json={"phone": "13800000000", "college": "信息中心"})

    # ---------- 会话记录 ----------
    def test_06_conversation_list(self):
        self.req("get", "/api/conversation/list", {200})

    def test_07_conversation_organize_requires_content(self):
        self.req("post", "/api/conversation/organize", {400}, json={})

    def test_08_conversation_batch_organize_requires_list(self):
        self.req("post", "/api/conversation/batch-organize", {400}, json={})

    def test_09_conversation_get_missing(self):
        self.req("get", "/api/conversation/99999999", {404})

    def test_10_conversation_delete_missing(self):
        self.req("delete", "/api/conversation/99999999", {200, 404})

    def test_11_recognize_image_requires_file(self):
        self.req("post", "/api/conversation/recognize-image", {400})

    def test_12_upload_document_requires_file(self):
        self.req("post", "/api/conversation/upload-document", {400})

    # ---------- 情绪 ----------
    def test_13_emotion_analyze_requires_file(self):
        self.req("post", "/api/emotion/analyze", {400})

    def test_14_emotion_batch_analyze_requires_list(self):
        self.req("post", "/api/emotion/batch-analyze", {400}, json={})

    def test_15_emotion_logs(self):
        self.req("get", "/api/emotion/logs", {200})

    def test_16_emotion_statistics(self):
        self.req("get", "/api/emotion/statistics", {200})

    def test_17_emotion_trends(self):
        self.req("get", "/api/emotion/trends", {200})

    def test_18_emotion_heatmap(self):
        self.req("get", "/api/emotion/heatmap", {200})

    def test_19_realtime_log(self):
        self.req("post", "/api/emotion/realtime-log", {200},
                 json={"student_name": "测试学生", "emotion": "焦虑", "intensity": 8, "confidence": 0.9})

    def test_20_realtime_call_summary(self):
        self.req("post", "/api/emotion/realtime-call-summary", {200},
                 json={"student_name": "测试学生", "samples": [
                     {"emotion": "焦虑", "intensity": 8, "confidence": 0.9}]})

    def test_21_yolo_detect_requires_image(self):
        self.req("post", "/api/emotion/yolo-detect", {400}, json={})

    def test_22_yolo_logs(self):
        self.req("get", "/api/emotion/yolo-logs", {200})

    def test_23_audio_chunk_requires_audio(self):
        self.req("post", "/api/emotion/audio-chunk", {400}, json={})

    def test_24_realtime_summary(self):
        self.req("get", "/api/emotion/realtime-summary", {200})

    def test_25_realtime_reset(self):
        self.req("post", "/api/emotion/realtime-reset", {200}, json={"session_id": "smoke_test"})

    # ---------- 预警 ----------
    def test_26_alert_list(self):
        self.req("get", "/api/alert/list", {200})

    def test_27_alert_statistics(self):
        self.req("get", "/api/alert/statistics", {200})

    def test_28_alert_acknowledge_missing(self):
        self.req("put", "/api/alert/99999999/acknowledge", {404})

    def test_29_alert_resolve_missing(self):
        self.req("put", "/api/alert/99999999/resolve", {404})

    # ---------- 知识库 ----------
    def test_30_knowledge_search(self):
        self.req("post", "/api/knowledge/search", {200}, json={"query": "心理咨询"})

    def test_31_knowledge_documents(self):
        self.req("get", "/api/knowledge/documents", {200})

    def test_32_knowledge_stats(self):
        self.req("get", "/api/knowledge/stats", {200})

    def test_33_knowledge_upload_requires_file(self):
        self.req("post", "/api/knowledge/upload", {400})

    # ---------- 系统 ----------
    def test_34_system_logs(self):
        self.req("get", "/api/system/logs", {200})

    def test_35_dashboard(self):
        self.req("get", "/api/system/dashboard", {200})

    # ---------- 学生 ----------
    def test_36_student_list(self):
        self.req("get", "/api/student/list", {200})

    def test_37_student_add_requires_fields(self):
        self.req("post", "/api/student/add", {400}, json={})

    def test_38_student_stats(self):
        self.req("get", "/api/student/stats", {200})

    def test_39_student_reminder_list(self):
        self.req("get", "/api/student/reminder/list", {200})

    def test_40_student_calendar(self):
        self.req("get", "/api/student/calendar", {200})

    def test_41_counselors_list(self):
        self.req("get", "/api/counselors/list", {200})

    # ---------- 工作台 ----------
    def test_42_workplan_today(self):
        self.req("get", "/api/workplan/today", {200})

    def test_43_workplan_day(self):
        self.req("get", "/api/workplan/day/2026-01-01", {200})

    def test_44_todo_add_requires_title(self):
        self.req("post", "/api/workplan/todo/add", {400}, json={})

    # ---------- 消息 ----------
    def test_45_message_contacts(self):
        self.req("get", "/api/messages/contacts", {200})

    def test_46_message_unread(self):
        self.req("get", "/api/messages/unread", {200})

    def test_47_message_send_requires_fields(self):
        self.req("post", "/api/messages/send", {400}, json={})

    def test_48_analyze_text_emotion(self):
        # 无 API key 时走本地关键词，有 key 时走 LLM，都应返回 200
        self.req("post", "/api/messages/analyze-emotion", {200},
                 json={"text": "最近压力很大，很焦虑"})

    def test_49_counselor_guidance_requires_messages(self):
        self.req("post", "/api/messages/counselor-guidance", {400}, json={})

    # ---------- 预约 ----------
    def test_50_appointments_list(self):
        self.req("get", "/api/appointments", {200})

    def test_51_appointment_create_student_only(self):
        # 管理员非学生身份，应 403
        self.req("post", "/api/appointments/create", {403},
                 json={"counselor_id": 1, "appointment_time": "2026-09-01T10:00:00"})

    # ---------- 导出 ----------
    def test_52_export_requires_type(self):
        self.req("post", "/api/data/export", {400}, json={})

    def test_53_export_conversations(self):
        r = self.req("post", "/api/data/export", {200, 400},
                     json={"type": "conversations", "format": "json"})
        self.assertNotEqual(r.status_code, 500)

    # ---------- 心理测评 ----------
    def test_54_assessment_student_only(self):
        self.req("post", "/api/assessment/submit", {400, 403}, json={"answers": []})

    def test_55_assessment_history(self):
        self.req("get", "/api/assessment/history", {200, 400})


if __name__ == "__main__":
    unittest.main(verbosity=2)
