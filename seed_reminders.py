import sys, os, random
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from core.database import DatabaseManager, Student, Reminder

db = DatabaseManager()

# ============================================================
# 先清空旧提醒数据
# ============================================================
with db.get_session() as session:
    session.query(Reminder).delete()
    session.commit()
    print("  已清空旧提醒数据")

# ============================================================
# 根据学生风险等级生成跟进提醒
# ============================================================
now = datetime.now()
today = now.replace(hour=9, minute=0, second=0, microsecond=0)

# 提醒类型和描述模板
high_risk_templates = [
    ("情绪跟进：{name} - 每日关怀谈话", "学生近期情绪状态为{emotion}，建议进行每日关怀谈话，了解最新状态"),
    ("心理评估：{name} - 本周心理量表", "高风险学生，建议本周安排一次心理量表评估"),
    ("家长沟通：{name} - 联系家长了解近况", "学生情绪波动较大，建议联系家长共同关注"),
    ("转介评估：{name} - 考虑专业心理咨询", "情绪持续不稳定，建议评估是否需要转介专业心理咨询"),
    ("学习关注：{name} - 了解学业近况", "高风险学生学业可能受影响，主动了解课程出勤和作业情况"),
]

medium_risk_templates = [
    ("周度跟进：{name} - 本周谈心谈话", "中风险学生，建议本周安排一次谈心谈话"),
    ("活动邀请：{name} - 参加减压活动", "邀请参加本周学院组织的心理减压活动"),
    ("宿舍走访：{name} - 了解宿舍生活", "中风险学生，走访宿舍了解日常生活状态"),
    ("同伴关注：{name} - 联系班干部了解", "请班干部留意该同学近期状态并反馈"),
]

low_risk_templates = [
    ("日常关怀：{name} - 例行问候", "低风险学生，发送一条关怀问候消息"),
]

reminder_dates = []
# 为未来30天生成提醒
for day_offset in range(-3, 31):
    reminder_dates.append(today + timedelta(days=day_offset))

with db.get_session() as session:
    students = session.query(Student).filter(Student.is_active == True).all()
    count = 0

    for student in students:
        risk = student.risk_level
        name = student.name

        if risk == "high":
            # 高风险：每天都有提醒，未来30天
            for d in reminder_dates:
                tmpl = random.choice(high_risk_templates)
                title = tmpl[0].format(name=name)
                desc = tmpl[1].format(name=name, emotion=student.emotion_status)
                reminder = Reminder(
                    student_id=student.id,
                    counselor_id=2,  # zhangwei
                    title=title,
                    description=desc,
                    reminder_type="emotion_check",
                    priority="high",
                    due_date=d.replace(hour=random.choice([9,10,14,15]), minute=random.choice([0,30])),
                    is_completed=(d.date() < now.date()),
                )
                session.add(reminder)
                count += 1

        elif risk == "medium":
            # 中风险：每周一提醒，未来30天
            for d in reminder_dates:
                if d.weekday() == 0:  # 周一
                    tmpl = random.choice(medium_risk_templates)
                    title = tmpl[0].format(name=name)
                    desc = tmpl[1].format(name=name)
                    reminder = Reminder(
                        student_id=student.id,
                        counselor_id=2,
                        title=title,
                        description=desc,
                        reminder_type="weekly_follow",
                        priority="medium",
                        due_date=d.replace(hour=10, minute=0),
                        is_completed=(d.date() < now.date()),
                    )
                    session.add(reminder)
                    count += 1

        else:
            # 低风险：每月1号例行关怀
            for d in reminder_dates:
                if d.day == 1:
                    tmpl = random.choice(low_risk_templates)
                    title = tmpl[0].format(name=name)
                    reminder = Reminder(
                        student_id=student.id,
                        counselor_id=2,
                        title=title,
                        description=f"低风险学生例行关怀",
                        reminder_type="routine",
                        priority="low",
                        due_date=d.replace(hour=9, minute=0),
                        is_completed=(d.date() < now.date()),
                    )
                    session.add(reminder)
                    count += 1

    session.commit()
    print(f"  成功生成 {count} 条跟进提醒")

    # 统计
    total = session.query(Reminder).count()
    pending = session.query(Reminder).filter(Reminder.is_completed == False).count()
    print(f"  提醒总数: {total}，待完成: {pending}")

    # 显示今天到期的
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today_end = today_start + timedelta(days=1)
    today_reminders = session.query(Reminder).filter(
        Reminder.due_date >= today_start,
        Reminder.due_date < today_end,
        Reminder.is_completed == False,
    ).all()
    print(f"\n  今日待办 ({len(today_reminders)} 条):")
    for r in today_reminders[:15]:
        stu = r.student.name if r.student else "?"
        print(f"    [{r.priority}] {r.title} ({stu}) - {r.due_date.strftime('%H:%M')}")
    if len(today_reminders) > 15:
        print(f"    ... 还有 {len(today_reminders)-15} 条")

print("\n  跟进提醒生成完成!")
