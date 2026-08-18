# -*- coding: utf-8 -*-
"""为每位辅导员生成差异化的工作待办和日历提醒"""
import sys, os, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from core.database import DatabaseManager, AuthManager

db = DatabaseManager()
auth = AuthManager(db)

# 每位辅导员的工作模板（按学院区分）
TEACHER_TASKS = {
    "张伟": {  # 计算机学院
        "college": "计算机学院",
        "work": [
            "整理计算机学院期中考试成绩单", "安排期末上机考试机房", "审核学生选课申请",
            "组织ACM编程竞赛报名", "联系企业安排暑期实习宣讲", "更新学院网站通知公告",
            "统计毕业生就业去向", "安排考研经验分享会", "整理学生科技创新项目申报",
            "实验室设备安全检查", "协调课程设计答辩安排", "汇总学生课堂出勤情况",
        ],
        "student_care": [
            "约谈挂科预警学生", "关注考研备考学生心理状态", "了解新生适应情况",
            "跟进经济困难学生助学金", "关怀少数民族学生学习生活",
        ],
    },
    "张老师": {  # 计算机学院
        "college": "计算机学院",
        "work": [
            "准备下周班会PPT材料", "填写本月辅导员工作月报", "整理学生入党申请书",
            "安排班级学风建设活动", "审核奖学金申请材料", "协调学生宿舍调整",
            "组织心理健康主题讲座", "统计学生第二课堂学分", "联系家委会沟通学生情况",
        ],
        "student_care": [
            "跟进心理测评异常学生", "关怀单亲家庭学生", "了解学习困难学生需求",
            "安排朋辈辅导员结对帮扶", "关注近期情绪波动学生",
        ],
    },
    "李老师": {  # 机械工程学院
        "college": "机械工程学院",
        "work": [
            "安排金工实习安全教育", "联系工厂安排参观实训", "整理毕业设计中期检查",
            "组织就业宣讲招聘会", "统计学生实训报告提交", "安排专业认证材料准备",
            "协调工程训练中心使用", "汇总学生创新项目进展", "安排学业导师见面会",
        ],
        "student_care": [
            "约谈学业预警学生面谈", "关注实训安全学生反馈", "了解毕业班就业焦虑",
            "跟进学生体检异常情况", "关怀校外实习学生生活",
        ],
    },
    "王老师": {  # 外国语学院
        "college": "外国语学院",
        "work": [
            "筹备外语文化节活动", "安排留学经验分享讲座", "整理晨读考勤记录",
            "组织英语演讲比赛初赛", "联系外教协调课程安排", "汇总学生海外交流申请",
            "安排翻译资格考试辅导", "统计语言实验室使用情况", "整理学生社团活动报告",
        ],
        "student_care": [
            "关注出国申请学生心理", "关怀少数民族预科生", "了解学生语言学习困难",
            "安排心理委员培训交流", "跟进学生课外活动参与度",
        ],
    },
}

def seed():
    print("=" * 60)
    print("为每位辅导员生成差异化工作待办")
    print("=" * 60)

    # 找到所有 counselor
    counselors = db.get_counselors()
    today = datetime.now()

    total_todos = 0
    total_reminders = 0

    for c in counselors:
        name = c["display_name"]
        if name not in TEACHER_TASKS:
            print(f"  [SKIP] {name} - 无任务模板")
            continue

        tasks = TEACHER_TASKS[name]
        print(f"\n  {name} ({tasks['college']})")

        # 生成工作待办（写入 todos 表）
        work_items = random.sample(tasks["work"], min(6, len(tasks["work"])))
        for i, title in enumerate(work_items):
            due = today + timedelta(days=random.randint(0, 14), hours=random.randint(8, 18))
            db.create_todo(
                user_id=c["id"],
                title=title,
                description="",
                category="work_task",
                priority=random.choice(["high", "medium", "medium", "low"]),
                due_date=due,
            )
            total_todos += 1

        # 生成学生关注待办
        care_items = random.sample(tasks["student_care"], min(3, len(tasks["student_care"])))
        for title in care_items:
            due = today + timedelta(days=random.randint(0, 7), hours=random.randint(8, 18))
            db.create_todo(
                user_id=c["id"],
                title=title,
                description="",
                category="student_care",
                priority=random.choice(["high", "medium", "medium"]),
                due_date=due,
            )
            total_todos += 1

        print(f"  [OK] {len(work_items)} 项工作 + {len(care_items)} 项学生关注 = {len(work_items)+len(care_items)} 条待办")

    print(f"\n{'=' * 60}")
    print(f"总计生成 {total_todos} 条待办事项")
    print(f"运行 'python app.py' 后刷新工作台即可查看")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    seed()
