# -*- coding: utf-8 -*-
"""
学生登录数据种子脚本
添加测试学生账号并设置密码
"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import DatabaseManager, AuthManager, Student, Base, engine
from werkzeug.security import generate_password_hash
from datetime import datetime

def seed_students_with_login():
    """添加学生数据并设置登录密码"""
    dm = DatabaseManager()
    am = AuthManager(dm)

    # 确保表存在
    dm.init_db()

    # 添加新列（如果不存在）
    import sqlite3
    db_path = "./data/campus_mind.db"
    if os.path.exists(db_path):
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        try:
            cursor.execute("ALTER TABLE students ADD COLUMN password_hash VARCHAR(256)")
            print("[OK] 添加 password_hash 列")
        except:
            pass
        try:
            cursor.execute("ALTER TABLE students ADD COLUMN email VARCHAR(100)")
            print("[OK] 添加 email 列")
        except:
            pass
        try:
            cursor.execute("ALTER TABLE students ADD COLUMN avatar VARCHAR(500)")
            print("[OK] 添加 avatar 列")
        except:
            pass
        try:
            cursor.execute("ALTER TABLE students ADD COLUMN last_login DATETIME")
            print("[OK] 添加 last_login 列")
        except:
            pass
        conn.commit()
        conn.close()

    # 测试学生数据
    test_students = [
        {"student_id": "2022001", "name": "王小明", "password": "123456", "gender": "男", "college": "计算机学院", "class_name": "计算机2022级1班", "phone": "13800001001"},
        {"student_id": "2022002", "name": "李思远", "password": "123456", "gender": "女", "college": "外语学院", "class_name": "外语2021级2班", "phone": "13800001002"},
        {"student_id": "2022003", "name": "张雨婷", "password": "123456", "gender": "女", "college": "文学院", "class_name": "中文2022级1班", "phone": "13800001003"},
        {"student_id": "2022004", "name": "陈浩然", "password": "123456", "gender": "男", "college": "数学学院", "class_name": "数学2022级1班", "phone": "13800001004"},
        {"student_id": "2022005", "name": "刘诗琪", "password": "123456", "gender": "女", "college": "艺术学院", "class_name": "美术2022级1班", "phone": "13800001005"},
        {"student_id": "2022006", "name": "赵天宇", "password": "123456", "gender": "男", "college": "计算机学院", "class_name": "计算机2022级2班", "phone": "13800001006"},
        {"student_id": "2022007", "name": "孙雅静", "password": "123456", "gender": "女", "college": "经济学院", "class_name": "经济2022级1班", "phone": "13800001007"},
        {"student_id": "2022008", "name": "周明辉", "password": "123456", "gender": "男", "college": "物理学院", "class_name": "物理2022级1班", "phone": "13800001008"},
        {"student_id": "2022009", "name": "吴佳琪", "password": "123456", "gender": "女", "college": "化学学院", "class_name": "化学2022级1班", "phone": "13800001009"},
        {"student_id": "2022010", "name": "郑浩宇", "password": "123456", "gender": "男", "college": "体育学院", "class_name": "体育2022级1班", "phone": "13800001010"},
    ]

    print("=" * 50)
    print("添加学生登录账号")
    print("=" * 50)

    with dm.get_session() as session:
        for stu_data in test_students:
            # 检查学生是否已存在
            existing = session.query(Student).filter(Student.student_id == stu_data["student_id"]).first()

            if existing:
                # 更新密码
                existing.password_hash = generate_password_hash(stu_data["password"], method="pbkdf2:sha256", salt_length=16)
                print(f"  [更新] {stu_data['student_id']} - {stu_data['name']} (密码已重置)")
            else:
                # 创建新学生
                student = Student(
                    student_id=stu_data["student_id"],
                    name=stu_data["name"],
                    password_hash=generate_password_hash(stu_data["password"], method="pbkdf2:sha256", salt_length=16),
                    gender=stu_data["gender"],
                    college=stu_data["college"],
                    class_name=stu_data["class_name"],
                    phone=stu_data["phone"],
                    risk_level="low",
                    emotion_status="正常",
                    is_active=True,
                )
                session.add(student)
                print(f"  [新增] {stu_data['student_id']} - {stu_data['name']}")

    print("\n" + "=" * 50)
    print("学生登录账号添加完成！")
    print("=" * 50)
    print("\n测试账号信息：")
    print("-" * 50)
    print(f"{'学号':<12}{'姓名':<10}{'密码':<12}{'学院'}")
    print("-" * 50)
    for stu in test_students:
        print(f"{stu['student_id']:<12}{stu['name']:<10}{stu['password']:<12}{stu['college']}")
    print("-" * 50)
    print("\n学生登录地址：http://localhost:5000")
    print('选择"学生登录"标签，使用上述学号和密码登录')


if __name__ == "__main__":
    seed_students_with_login()
