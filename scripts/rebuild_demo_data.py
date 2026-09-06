# -*- coding: utf-8 -*-
"""聆心 · 演示数据重建（重置全库后重建答辩演示亮点数据）

用法：
    python scripts/rebuild_demo_data.py [BASE_URL]
    # BASE_URL 默认 http://127.0.0.1:5000；线上用 https://8.153.151.13（-k 自签证书见 verify）

流程：管理员触发全库重置（清空洪水/污染数据）→ 重建演示亮点：
    ① 全部辅导员开启 AI 数字人
    ② 郭诗雨高分测评（生成危机预警 + 测评证据）
    ③ 三条预约（待确认/已确认/已完成，联动档案与待办）
    ④ 学生发消息触发 AI 分身回复（数字人值班数据）
    ⑤ 谈心报告（生成 talk_report 证据，形成多来源时间线）
"""
import json
import ssl
import sys
import urllib.request
import urllib.error
from datetime import datetime, timedelta

BASE = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:5000").rstrip("/")
CTX = ssl._create_unverified_context() if BASE.startswith("https") else None

def req(method, path, token=None, payload=None, timeout=180):
    r = urllib.request.Request(BASE + path, method=method)
    r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    try:
        with urllib.request.urlopen(r, data=data, timeout=timeout, context=CTX) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": str(e)}

def login(username, password):
    s, d = req("POST", "/api/auth/login", payload={"username": username, "password": password})
    if s != 200 or not d.get("data", {}).get("token"):
        raise SystemExit(f"登录失败 {username}: {s}")
    return d["data"]["token"]

def student_login(sid, password="123456"):
    s, d = req("POST", "/api/student/login", payload={"student_id": sid, "password": password})
    if s != 200 or not d.get("data", {}).get("token"):
        raise SystemExit(f"学生登录失败 {sid}: {s}")
    return d["data"]["token"]

print("== 1/6 管理员登录并全库重置（约 30-90 秒）==")
admin = login("admin", "admin123")
s, d = req("POST", "/api/system/reseed", admin, timeout=240)
print("   reseed:", s, d.get("message", ""))
if s != 200:
    raise SystemExit("重置失败，中止")

s, d = req("GET", "/api/student/list?page=1&per_page=1", admin)
total = d.get("total", 0)
print("   重置后学生总数:", total, "（应为 600）")
if total != 600:
    raise SystemExit("学生数异常，中止")

print("== 2/6 辅导员登录并开启 AI 数字人 ==")
_, cl = req("GET", "/api/system/test-accounts", admin)
counselors = [(c["username"], "counsel123") for c in cl["data"]["counselors"]]
for uname, pwd in counselors[:3]:  # 前 3 位辅导员开启数字人（演示主力账号）
    t = login(uname, pwd)
    s, _ = req("PUT", "/api/digital-human/settings", t,
               payload={"enabled": True, "name": "小聆", "humor": 3, "style": "humor", "delay": 2})
    print(f"   {uname} 数字人开启: {s}")
zw_token = login(counselors[0][0], counselors[0][1])

print("== 3/6 郭诗雨高分测评（危机预警 + 测评证据）==")
s, d = req("GET", "/api/student/list?page=1&per_page=50", zw_token)
data = d.get("data")
items = data.get("items") if isinstance(data, dict) else data
items = items or []
guo = next((x for x in items if x.get("student_id") == "20230035"), None)
if not guo:
    raise SystemExit("未找到郭诗雨(20230035)")
answers = [{"q": i + 1, "a": a} for i, a in enumerate([2, 2, 2, 2, 1, 2, 1, 1, 2, 2, 2, 2, 1, 2, 1, 1, 2, 1, 2, 1, 1, 1, 1])]
s, d = req("POST", "/api/assessment/submit", student_login("20230035"),
           payload={"answers": answers, "duration_seconds": 240})
print("   测评提交:", s, "| 危机预警:", d.get("data", {}).get("crisis"))

print("== 4/6 三条预约（待确认/已确认/已完成）==")
st = student_login("20230035")
now = datetime.now()
mk = lambda day, hour: (now + __import__("datetime").timedelta(days=day)).strftime("%Y-%m-%d") + f" {hour:02d}:00"
appt_ids = []
for day, hour, reason in [(1, 14, "近期学业压力较大，想找老师聊聊复习规划"),
                          (2, 10, "连续两周失眠，想咨询改善睡眠的方法"),
                          (3, 16, "和室友闹了些矛盾，情绪有点低落")]:
    s, d = req("POST", "/api/appointments/create", st,
               payload={"counselor_id": guo["counselor_id"], "appointment_time": mk(day, hour), "reason": reason})
    appt_ids.append(d.get("data", {}).get("id"))
    print(f"   预约创建: {s} id={d.get('data', {}).get('id')}")
s, _ = req("PUT", f"/api/appointments/{appt_ids[1]}/status", zw_token, payload={"status": "confirmed"})
print("   预约2确认:", s)
s, _ = req("PUT", f"/api/appointments/{appt_ids[2]}/status", zw_token,
           payload={"status": "completed", "notes": "面谈 45 分钟，学生倾诉顺畅，已共同制定情绪调适计划"})
print("   预约3完成:", s)

print("== 5/6 学生发消息触发 AI 分身回复 ==")
msg = "老师，我最近总是很焦虑，晚上也睡不好，白天上课也集中不了精神，您有什么建议吗？"
s, d = req("POST", "/api/messages/send", st, payload={"contact_id": guo["counselor_id"], "content": msg})
print("   消息发送:", s, "（老师离线，AI 分身将自动回复）")

print("== 6/6 谈心报告（talk_report 证据，形成多来源时间线）==")
msgs = [
    {"sender_type": "student", "content": "老师，最近考试压力好大，晚上翻来覆去睡不着"},
    {"sender_type": "counselor", "content": "睡眠问题要重视，先试试睡前不玩手机、喝杯热牛奶，我们一步步来"},
    {"sender_type": "student", "content": "嗯嗯，我试试。就是一想到下周的考试就心慌"},
    {"sender_type": "counselor", "content": "把复习拆成小任务，每天完成一点，焦虑会小很多"},
]
s, d = req("POST", "/api/conversation/generate-report", zw_token,
           payload={"student_id": guo["id"], "student_name": "郭诗雨", "topic": "学业压力与睡眠", "messages": msgs})
print("   谈心报告:", s, "| 风险判定:", d.get("data", {}).get("report", {}).get("risk_level"))

print("\n== 重建完成 ==  等待 2 分钟内完成 AI 分身回复后即可用于演示。")
