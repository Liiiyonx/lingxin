# -*- coding: utf-8 -*-
"""补充辅导员和学工人员到数据库"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import DatabaseManager, AuthManager

db = DatabaseManager()
auth = AuthManager(db)

extra_users = [
    ("zhangsan", "123456", "counselor", "张老师", "计算机学院"),
    ("lisi", "123456", "counselor", "李老师", "机械工程学院"),
    ("wangwu", "123456", "counselor", "王老师", "外国语学院"),
    ("liuxin", "staff123", "student_affairs", "刘鑫", "学生工作处"),
    ("student_affairs", "123456", "student_affairs", "学工处管理员", "学生工作处"),
]

print("=" * 50)
print("添加辅导员和学工人员")
print("=" * 50)

for uname, pwd, role, display, college in extra_users:
    try:
        uid = auth.create_user(uname, pwd, role, display, college)
        print(f"  [OK] {display} ({uname}) - id={uid}")
    except Exception as e:
        print(f"  [SKIP] {uname}: {e}")

print("\n当前所有用户：")
users = db.search_users(per_page=50)
for u in users.get("items", []):
    print(f"  [{u['role']}] {u['display_name']} ({u['username']}) - {u['college']}")

print("\n完成！")
