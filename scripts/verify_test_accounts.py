# -*- coding: utf-8 -*-
"""
聆心 — 测试账号数据一致性校验脚本

逐账号校验：
  1. 教师端账号（admin / 学工处 / 辅导员）是否存在、角色是否正确、能否登录
  2. 每名辅导员是否固定 50 名学生
  3. 学生账号（学号 + 密码 123456）能否登录
  4. 学生学号唯一性、情绪/风险取值合法性、外键关联完整性
  5. 是否残留无用账号（zhangsan/lisi/wangwu/xuegong01/xuegong02）
  6. 登录页动态下发接口的数据是否与库一致

运行: python scripts/verify_test_accounts.py
"""
import sys, os
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, '.')

from datetime import datetime
from werkzeug.security import check_password_hash
from core.database import (
    DatabaseManager, AuthManager, User, Student, Message, EmotionLog,
    AlertLog, Reminder, EmotionTracker, StudentProfile, EMOTION_NETWORK_META,
)

db = DatabaseManager()
auth = AuthManager(db)

PASS = 0
FAIL = 0
ERRORS = []


def check(cond, label, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {label}")
    else:
        FAIL += 1
        ERRORS.append(label + (" | " + detail if detail else ""))
        print(f"  [FAIL] {label}  {detail}")


def section(title):
    print("\n" + "=" * 68)
    print(" " + title)
    print("=" * 68)


VALID_RISK = {"low", "medium", "high"}
VALID_EMOTIONS = set(EMOTION_NETWORK_META.keys())


def main():
    section("1. 教师端账号（管理员 / 学工处）")
    staff_expect = [
        ("admin", "admin123", "super_admin"),
        ("liuxin", "staff123", "student_affairs"),
        ("student_affairs", "staff123", "student_affairs"),
    ]
    with db.get_session() as session:
        for uname, pwd, role in staff_expect:
            user = auth.authenticate(uname, pwd)
            check(user is not None, f"{uname} 可登录", f"用户名={uname}")
            if user is not None:
                check(user.get("role") == role, f"{uname} 角色={role}", f"实际={user.get('role')}")

    section("2. 辅导员账号（12 人，密码 counsel123）")
    with db.get_session() as session:
        _counselors = session.query(User).filter(User.role == "counselor", User.is_active == True).all()
        counselors = [{"id": c.id, "username": c.username, "display_name": c.display_name} for c in _counselors]
    check(len(counselors) == 12, f"辅导员数量=12", f"实际={len(counselors)}")
    for c in counselors:
        ok = auth.authenticate(c["username"], "counsel123") is not None
        check(ok, f"{c['username']}（{c['display_name']}）可登录")

    section("3. 每名辅导员固定 50 名学生")
    with db.get_session() as session:
        for c in counselors:
            cnt = session.query(Student.id).filter(Student.counselor_id == c["id"], Student.is_active == True).count()
            check(cnt == 50, f"{c['username']} 学生数=50", f"实际={cnt}")

    section("4. 学生账号（学号唯一 + 密码 123456 可登录）")
    with db.get_session() as session:
        _students = session.query(Student).filter(Student.is_active == True).all()
        students = [{"id": s.id, "student_id": s.student_id, "name": s.name,
                     "emotion_status": s.emotion_status, "risk_level": s.risk_level,
                     "password_hash": s.password_hash} for s in _students]
    total = len(students)
    check(total == 600, "学生总数=600", f"实际={total}")

    ids = [s["student_id"] for s in students]
    check(len(ids) == len(set(ids)), "学号唯一", f"重复学号数={len(ids)-len(set(ids))}")

    # 密码可用性：抽查 + 全量校验哈希存在
    no_pwd = [s for s in students if not s["password_hash"]]
    check(len(no_pwd) == 0, "所有学生均有密码哈希", f"缺失={len(no_pwd)}")

    login_ok = 0
    for s in students[:30]:  # 抽查前 30 名学生登录
        if auth.authenticate_student(s["student_id"], "123456") is not None:
            login_ok += 1
    check(login_ok == 30, "抽查 30 名学生均可登录(123456)", f"成功={login_ok}/30")

    # 全量校验密码哈希可匹配 123456
    pwd_mismatch = 0
    for s in students:
        if not s.get("password_hash") or not check_password_hash(s["password_hash"], "123456"):
            pwd_mismatch += 1
    check(pwd_mismatch == 0, "全量密码哈希匹配 123456", f"不匹配/缺失={pwd_mismatch}")

    section("5. 学生情绪/风险取值合法性")
    bad_emo = [s["student_id"] for s in students if s["emotion_status"] not in VALID_EMOTIONS]
    check(len(bad_emo) == 0, "emotion_status 取值合法", f"非法={bad_emo[:10]}")
    bad_risk = [s["student_id"] for s in students if s["risk_level"] not in VALID_RISK]
    check(len(bad_risk) == 0, "risk_level 取值合法", f"非法={bad_risk[:10]}")

    section("6. 无残留无用账号")
    with db.get_session() as session:
        strays = session.query(User).filter(User.username.in_(["zhangsan", "lisi", "wangwu", "xuegong01", "xuegong02"])).all()
        stray_names = [u.username for u in strays]
    check(len(stray_names) == 0, "无残留账号(zhangsan/lisi/wangwu/xuegong01/02)", f"残留={stray_names}")

    section("7. 外键关联完整性（消息/情绪日志/预警/提醒）")
    with db.get_session() as session:
        valid_student_ids = set(s["id"] for s in students)
        valid_user_ids = set(u.id for u in session.query(User).all())

        orphan_msgs = session.query(Message).filter(~Message.student_id.in_(valid_student_ids)).count() \
            if valid_student_ids else 0
        orphan_logs = session.query(EmotionLog).filter(~EmotionLog.analyzed_by.in_(valid_user_ids)).count() \
            if valid_user_ids else 0
        orphan_alerts = session.query(AlertLog).filter(~AlertLog.assigned_to.in_(valid_user_ids)).count() \
            if valid_user_ids else 0
        orphan_rem = session.query(Reminder).filter(~Reminder.student_id.in_(valid_student_ids)).count() \
            if valid_student_ids else 0
    check(orphan_msgs == 0, "消息无孤儿 student_id", f"孤儿={orphan_msgs}")
    check(orphan_logs == 0, "情绪日志无孤儿 analyzed_by", f"孤儿={orphan_logs}")
    check(orphan_alerts == 0, "预警无孤儿 assigned_to", f"孤儿={orphan_alerts}")
    check(orphan_rem == 0, "提醒无孤儿 student_id", f"孤儿={orphan_rem}")

    section("8. 登录页动态下发接口数据一致性")
    acc = db.get_test_accounts()
    check(len(acc.get("staff", [])) >= 3, "学工处/管理员账号≥3", f"实际={len(acc.get('staff', []))}")
    check(len(acc.get("counselors", [])) == 12, "辅导员账号=12", f"实际={len(acc.get('counselors', []))}")
    for c in acc.get("counselors", []):
        check(len(c.get("students", [])) == 3, f"{c['username']} 示例学生=3", f"实际={len(c.get('students', []))}")

    section("9. 情绪网络图数据抽查")
    net = db.get_emotion_network()
    check(net["stats"]["total"] == 600, "网络图统计 total=600", f"实际={net['stats']['total']}")
    check(sum(g["count"] for g in net["groups"]) == 600, "网络图分组计数之和=600",
          f"实际={sum(g['count'] for g in net['groups'])}")
    # 辅导员视角（取第一个辅导员）
    first_counselor = counselors[0]["id"]
    net2 = db.get_emotion_network(counselor_id=first_counselor, role="counselor")
    check(net2["stats"]["total"] == 50, "辅导员视角网络图=50 名学生", f"实际={net2['stats']['total']}")
    check(net2["root"]["name"] == counselors[0]["display_name"], "辅导员视角中心节点为本人", f"实际={net2['root']['name']}")

    print("\n" + "=" * 68)
    print(f"  校验完成：通过 {PASS} 项，失败 {FAIL} 项")
    if ERRORS:
        print("  失败项明细：")
        for e in ERRORS:
            print(f"    - {e}")
    print("=" * 68)
    sys.exit(1 if FAIL else 0)


if __name__ == "__main__":
    main()
