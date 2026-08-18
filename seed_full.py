import sys, os, random
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(r'C:\Users\Liii\Desktop\聆心-代码文件')
sys.path.insert(0, '.')

from datetime import datetime, timedelta
from core.database import DatabaseManager, Student, Reminder

db = DatabaseManager()
now = datetime.now()
today = now.replace(hour=9, minute=0, second=0, microsecond=0)

with db.get_session() as session:
    # Clear old reminders
    session.query(Reminder).delete()
    session.commit()

    students = session.query(Student).filter(Student.is_active == True).all()
    high_students = [s for s in students if s.risk_level == 'high']
    medium_students = [s for s in students if s.risk_level == 'medium']
    print(f"  Students: {len(high_students)} high, {len(medium_students)} medium")

    counselor_tasks = [
        {"title": "学院学生工作例会", "desc": "每周一次的学院学生工作会议，汇报本周工作进展", "type": "meeting", "priority": "medium", "weekday": 0, "hour": 14},
        {"title": "心理危机干预研判会", "desc": "与心理咨询中心联合研判近期重点关注学生情况", "type": "meeting", "priority": "high", "weekday": 2, "hour": 10},
        {"title": "辅导员业务培训", "desc": "学生处组织的辅导员能力提升培训", "type": "training", "priority": "low", "weekday": 4, "hour": 15},
        {"title": "班会：期末考试诚信教育", "desc": "期末考试季，开展诚信考试主题班会", "type": "class_meeting", "priority": "medium", "weekday": 1, "hour": 19},
        {"title": "班会：暑期安全教育", "desc": "放假前安全注意事项，防溺水、防诈骗", "type": "class_meeting", "priority": "high", "weekday": 3, "hour": 19},
        {"title": "宿舍走访值班", "desc": "晚间宿舍走访，了解学生生活状态", "type": "duty", "priority": "medium", "weekday": 0, "hour": 21},
        {"title": "宿舍走访值班", "desc": "晚间宿舍走访，了解学生生活状态", "type": "duty", "priority": "medium", "weekday": 2, "hour": 21},
        {"title": "宿舍走访值班", "desc": "晚间宿舍走访，了解学生生活状态", "type": "duty", "priority": "medium", "weekday": 4, "hour": 21},
        {"title": "审批：学生请假条", "desc": "处理本周积压的学生请假申请", "type": "document", "priority": "medium", "weekday": 0, "hour": 10},
        {"title": "提交：学生月度思想汇报", "desc": "向学生处提交本月学生思想动态报告", "type": "document", "priority": "high", "weekday": 4, "hour": 17},
        {"title": "心理健康周报", "desc": "整理本周学生心理健康情况，上报学院", "type": "report", "priority": "medium", "weekday": 4, "hour": 16},
        {"title": "重点关注学生家长沟通", "desc": "与高风险学生家长电话沟通近期情况", "type": "follow_up", "priority": "high", "weekday": 3, "hour": 10},
    ]

    count = 0
    placeholder_id = students[0].id

    for day_offset in range(-3, 31):
        d = today + timedelta(days=day_offset)
        weekday = d.weekday()

        # Fixed weekly tasks
        for task in counselor_tasks:
            if task["weekday"] == weekday:
                session.add(Reminder(
                    student_id=placeholder_id, counselor_id=2,
                    title=task["title"], description=task["desc"],
                    reminder_type=task["type"], priority=task["priority"],
                    due_date=d.replace(hour=task["hour"], minute=0),
                    is_completed=(d.date() < now.date()),
                ))
                count += 1

        # High risk: daily
        for s in high_students:
            templates = [
                ("情绪跟进：{n} - 每日关怀谈话", "学生近期情绪状态为{e}，建议每日关怀谈话"),
                ("心理评估：{n} - 本周心理量表", "高风险学生，建议安排心理量表评估"),
                ("家长沟通：{n} - 联系家长了解近况", "情绪波动较大，建议联系家长共同关注"),
            ]
            t = random.choice(templates)
            session.add(Reminder(
                student_id=s.id, counselor_id=2,
                title=t[0].format(n=s.name), description=t[1].format(n=s.name, e=s.emotion_status),
                reminder_type="emotion_check", priority="high",
                due_date=d.replace(hour=random.choice([9,10,14,15]), minute=random.choice([0,30])),
                is_completed=(d.date() < now.date()),
            ))
            count += 1

        # Medium risk: weekly Monday
        if weekday == 0:
            for s in medium_students:
                templates = [
                    ("周度跟进：{n} - 本周谈心谈话", "中风险学生，建议本周安排谈心谈话"),
                    ("活动邀请：{n} - 参加减压活动", "邀请参加本周心理减压活动"),
                    ("宿舍走访：{n} - 了解宿舍生活", "走访宿舍了解日常生活状态"),
                ]
                t = random.choice(templates)
                session.add(Reminder(
                    student_id=s.id, counselor_id=2,
                    title=t[0].format(n=s.name), description=t[1].format(n=s.name),
                    reminder_type="weekly_follow", priority="medium",
                    due_date=d.replace(hour=10, minute=0),
                    is_completed=(d.date() < now.date()),
                ))
                count += 1

    session.commit()
    total = session.query(Reminder).count()
    pending = session.query(Reminder).filter(Reminder.is_completed == False).count()
    print(f"  Generated {count} reminders, Total: {total}, Pending: {pending}")
    print("  Done!")
