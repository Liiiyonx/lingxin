# -*- coding: utf-8 -*-
"""
聆心 — 全账号逐个实测脚本
=========================
对演示环境中的每一个账号做「真实 HTTP 登录 + 角色核心接口逐个请求」的冒烟验证：

- 教师端（管理员 / 学工处 / 全部辅导员）：逐个登录并请求其角色可见的核心接口；
- 学生端：对登录页动态下发的示例学生逐个登录并请求学生端核心接口；
  学生登录接口受 IP 限流（30 次 / 5 分钟），可用 --offset/--limit 分批执行，
  分批之间重启服务即可清除限流计数。

用法：
    python scripts/test_all_accounts.py staff
    python scripts/test_all_accounts.py students --offset 0 --limit 18
    python scripts/test_all_accounts.py students --offset 18 --limit 18
"""
import argparse
import json
import sys
import urllib.request
import urllib.error

BASE = "http://127.0.0.1:5000"

STAFF_PASSWORDS = {
    "super_admin": "admin123",
    "student_affairs": "staff123",
    "counselor": "counsel123",
}
STUDENT_PASSWORD = "123456"

STAFF_ENDPOINTS = {
    "super_admin": [
        "/api/system/dashboard", "/api/system/logs", "/api/alert/crisis-center",
        "/api/knowledge/stats", "/api/student/list", "/api/messages/contacts",
        "/api/workplan/today", "/api/network/emotion-graph",
    ],
    "student_affairs": [
        "/api/system/dashboard", "/api/alert/crisis-center", "/api/student/list",
        "/api/emotion/statistics", "/api/messages/contacts", "/api/workplan/today",
    ],
    "counselor": [
        "/api/workplan/today", "/api/system/dashboard", "/api/alert/list",
        "/api/student/list", "/api/messages/contacts", "/api/appointments",
        "/api/student/reminder/list", "/api/network/emotion-graph",
    ],
}
STUDENT_ENDPOINTS = [
    "/api/student/profile", "/api/emotion/trends", "/api/assessment/history",
    "/api/appointments", "/api/counselors/list", "/api/messages/contacts",
    "/api/messages/unread",
]


def http_json(method, path, token=None, payload=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    try:
        with urllib.request.urlopen(req, data=data, timeout=30) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read().decode("utf-8") or "{}")
        except Exception:
            body = {}
        return e.code, body


def check_endpoints(name, token, paths, extra_query=""):
    """逐个请求接口，返回失败列表。"""
    failures = []
    for p in paths:
        status, body = http_json("GET", p + (extra_query if p.endswith("trends") else ""), token)
        if status != 200:
            failures.append(f"{p}->{status}")
    return failures


def test_staff():
    _, data = http_json("GET", "/api/system/test-accounts")
    accounts = data["data"]
    rows = []
    failed_total = 0

    for item in accounts["staff"]:
        username, role = item["username"], item["role"]
        pwd = STAFF_PASSWORDS[role]
        status, body = http_json("POST", "/api/auth/login",
                                 payload={"username": username, "password": pwd})
        if status != 200 or not body.get("data", {}).get("token"):
            rows.append((role, username, "登录失败", f"HTTP {status}"))
            failed_total += 1
            continue
        token = body["data"]["token"]
        fails = check_endpoints(username, token, STAFF_ENDPOINTS[role])
        rows.append((role, username, "通过" if not fails else "部分失败",
                     "全部核心接口 200" if not fails else "; ".join(fails)))
        failed_total += 1 if fails else 0

    for c in accounts["counselors"]:
        username, role = c["username"], "counselor"
        status, body = http_json("POST", "/api/auth/login",
                                 payload={"username": username, "password": STAFF_PASSWORDS[role]})
        if status != 200 or not body.get("data", {}).get("token"):
            rows.append((role, username, "登录失败", f"HTTP {status}"))
            failed_total += 1
            continue
        token = body["data"]["token"]
        # 附加校验：该辅导员学生列表应恰好返回其管辖学生（student_count）
        _, sl = http_json("GET", "/api/student/list", token)
        student_total = sl.get("total", -1) if status == 200 else -1
        count_ok = (student_total == c["student_count"])
        fails = check_endpoints(username, token, STAFF_ENDPOINTS[role])
        note = f"学生数 {student_total}/{c['student_count']}{'✓' if count_ok else '✗'}"
        if fails:
            note += "; " + "; ".join(fails)
        rows.append((role, username, "通过" if (not fails and count_ok) else "异常", note))
        failed_total += 0 if (not fails and count_ok) else 1

    print("\n===== 教师端账号实测结果 =====")
    print(f"{'角色':<16}{'账号':<18}{'结果':<10}详情")
    for role, username, verdict, note in rows:
        print(f"{role:<16}{username:<18}{verdict:<10}{note}")
    print(f"\n合计 {len(rows)} 个教师端账号，异常 {failed_total} 个")
    return failed_total


def test_students(offset, limit):
    _, data = http_json("GET", "/api/system/test-accounts")
    accounts = data["data"]
    samples = []
    for c in accounts["counselors"]:
        for s in c["students"]:
            samples.append({"counselor": c["display_name"], **s})
    picked = samples[offset:offset + limit]
    rows = []
    failed_total = 0

    for s in picked:
        sid = s["student_id"]
        status, body = http_json("POST", "/api/student/login",
                                 payload={"student_id": sid, "password": STUDENT_PASSWORD})
        if status != 200 or not body.get("data", {}).get("token"):
            rows.append((s["counselor"], sid, s["name"], "登录失败", f"HTTP {status}"))
            failed_total += 1
            continue
        token = body["data"]["token"]
        fails = []
        for p in STUDENT_ENDPOINTS:
            path = p + (f"?student_id={sid}" if p.endswith("trends") else "")
            st, _ = http_json("GET", path, token)
            if st != 200:
                fails.append(f"{p}->{st}")
        rows.append((s["counselor"], sid, s["name"], "通过" if not fails else "部分失败",
                     "全部学生端接口 200" if not fails else "; ".join(fails)))
        failed_total += 1 if fails else 0

    print("\n===== 学生端账号实测结果 =====")
    print(f"{'辅导员':<10}{'学号':<12}{'姓名':<8}{'结果':<10}详情")
    for counselor, sid, name, verdict, note in rows:
        print(f"{counselor:<10}{sid:<12}{name:<8}{verdict:<10}{note}")
    print(f"\n本批 {len(picked)} 个学生账号，异常 {failed_total} 个（登录页示例学生共 {len(samples)} 个）")
    return failed_total


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("mode", choices=["staff", "students"])
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=18)
    args = parser.parse_args()
    failures = test_staff() if args.mode == "staff" else test_students(args.offset, args.limit)
    sys.exit(1 if failures else 0)
