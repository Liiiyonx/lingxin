# -*- coding: utf-8 -*-
"""
聆心 v3.2 — 完整种子数据脚本（确定性）
创建辅导员、学生、工作台数据，建立辅导员-班级-学生关联关系
- 固定随机种子，保证每次运行数据完全一致（学号/姓名/辅导员严格对应）
- 每名辅导员固定 50 名学生（满足网络图美观性）
- 清理历史遗留的无用账号（zhangsan/lisi/wangwu/xuegong01/xuegong02）
运行: python seed_v31.py
"""
import sys, os, random
sys.stdout.reconfigure(encoding='utf-8')
os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

# 固定随机种子：保证数据确定性
random.seed(20240819)

from datetime import datetime, timedelta
from werkzeug.security import generate_password_hash
from core.database import (
    DatabaseManager, AuthManager, Student, User, Reminder, Todo,
    EmotionLog, AlertLog, EmotionTracker, Message, Appointment,
    ConversationRecord, SystemLog, StudentProfile, AssessmentResult,
)

db = DatabaseManager()
auth = AuthManager(db)
now = datetime.now()
today = now.replace(hour=9, minute=0, second=0, microsecond=0)

# ═══════════════════════════════════════════════════════════
#  1. 账号组织结构定义
# ═══════════════════════════════════════════════════════════
# 学工处 / 管理员（固定账号）
STAFF_ACCOUNTS = [
    ("admin", "admin123", "系统管理员", "super_admin", "信息中心"),
    ("liuxin", "staff123", "刘鑫", "student_affairs", "学生工作处"),
    ("student_affairs", "staff123", "学工处管理员", "student_affairs", "学生工作处"),
]

# 辅导员：每名固定 50 名学生（由 TOTAL_STUDENTS_PER_COUNSELOR 控制）
COLLEGE_COUNSELORS = [
    # (用户名, 密码, 显示名, 学院, 管理班级列表)
    ("zhangwei",   "counsel123", "张伟",   "计算机学院",   ["2024级计算机1班", "2024级计算机2班", "2023级计算机1班"]),
    ("liuqiang",   "counsel123", "刘强",   "计算机学院",   ["2024级计算机3班", "2023级计算机2班", "2022级计算机1班"]),
    ("wangli",     "counsel123", "王莉",   "机械工程学院", ["2024级机械1班", "2024级机械2班", "2023级机械1班"]),
    ("zhaolei",    "counsel123", "赵磊",   "机械工程学院", ["2023级机械2班", "2022级机械1班"]),
    ("chenjing",   "counsel123", "陈静",   "外国语学院",   ["2024级英语1班", "2024级英语2班", "2023级英语1班"]),
    ("yangfan",    "counsel123", "杨帆",   "外国语学院",   ["2024级日语1班", "2023级英语2班", "2022级英语1班"]),
    ("huangwei",   "counsel123", "黄薇",   "经济管理学院", ["2024级工商1班", "2024级会计1班", "2023级工商1班"]),
    ("zhoujie",    "counsel123", "周杰",   "经济管理学院", ["2024级金融1班", "2023级会计1班"]),
    ("sunpeng",    "counsel123", "孙鹏",   "电子工程学院", ["2024级电子1班", "2024级通信1班", "2023级电子1班"]),
    ("wuxiaolin",  "counsel123", "吴晓琳", "电子工程学院", ["2024级通信2班", "2023级通信1班"]),
    ("zhengyu",    "counsel123", "郑宇",   "文学院",       ["2024级中文1班", "2024级新闻1班", "2023级中文1班"]),
    ("tangli",     "counsel123", "唐丽",   "艺术学院",     ["2024级设计1班", "2024级美术1班", "2023级设计1班"]),
]

# 历史遗留无用账号，统一清理
STRAY_USERNAMES = ["zhangsan", "lisi", "wangwu", "xuegong01", "xuegong02"]

# ═══════════════════════════════════════════════════════════
#  2. 学生数据配置
# ═══════════════════════════════════════════════════════════
TOTAL_STUDENTS_PER_COUNSELOR = 50   # 每名辅导员固定 50 名学生
STUDENT_DEFAULT_PASSWORD = "123456"

EMOTIONS = ["正常", "高兴", "低落", "焦虑", "烦躁", "压抑", "愤怒", "紧张", "悲伤"]
EMOTION_WEIGHTS = [30, 18, 10, 8, 6, 5, 3, 5, 5]
RISK_LEVELS_WEIGHTED = ["low"] * 60 + ["medium"] * 28 + ["high"] * 12  # 12%高 + 28%中 + 60%低
DEMO_EMOTION_LOGS_PER_STUDENT = 3

# 每个班级的学生姓名池
MALE_NAMES = ["王明远","李浩宇","张子轩","刘俊杰","陈一鸣","杨思源","赵文博","黄志豪","周睿阳","吴泽宇",
              "徐浩然","孙旭东","胡天宇","朱泽洋","高铭远","林嘉诚","何志强","郭晨阳","马思远","罗浩然",
              "梁子涵","宋逸飞","郑凯文","谢宇航","韩明哲","唐宇轩","冯志伟","于俊豪","董昊然","萧睿",
              "程子健","曹天磊","袁伟杰","邓博文","许鸿飞","傅明辉","沈宇辰","曾子墨","彭浩然","吕思源"]
FEMALE_NAMES = ["李思雨","王梓涵","张雨彤","刘梦瑶","陈诗涵","杨欣怡","赵雅琪","黄雨薇","周思琪","吴佳妮",
                "徐雅馨","孙晓萌","胡梓萱","朱雨晴","高雨欣","林悦然","何静怡","郭诗雨","马晓婷","罗梦洁",
                "梁雨霏","宋美琳","郑思颖","谢雨彤","韩佳琪","唐晓柔","冯雅楠","于思源","董怡然","萧雨桐",
                "程子萱","曹雨晨","袁梦琪","邓欣怡","许诺言","傅雅琪","沈佳怡","曾雨馨","彭思琪","吕婉清"]

# 学生备注库
NOTES_POOL = [
    "", "", "", "", "", "", "",
    "学业压力较大，需要关注期末复习状态",
    "性格内向，建议多参加集体活动",
    "家庭经济困难，已申请国家助学金",
    "体育特长生，需平衡训练与学业",
    "担任班长，工作积极主动负责",
    "入党积极分子，思想政治表现优秀",
    "上学期有挂科，需重点关注学业",
    "宿舍人际关系融洽，心理健康状态良好",
    "转专业学生，适应期需要特别关注",
    "毕业生，面临考研与就业双重压力",
    "心理普查显示轻度焦虑，建议定期谈心",
    "曾因家庭变故申请临时困难补助",
    "学业优秀，获得国家奖学金",
    "睡眠质量差，经常熬夜打游戏",
    "与室友关系紧张，已调解一次",
]

# ═══════════════════════════════════════════════════════════
#  3. 工作台提醒模板
# ═══════════════════════════════════════════════════════════
REMINDER_TEMPLATES = [
    # (标题模板, 描述模板, 类型, 优先级, 星期几, 小时)
    ("学院学生工作例会", "每周学院学生工作会议，汇报本周工作进展", "meeting", "medium", 0, 14),
    ("心理危机干预研判会", "与心理咨询中心联合研判近期重点关注学生", "meeting", "high", 2, 10),
    ("辅导员业务培训", "学生处组织的辅导员能力提升专题培训", "training", "low", 4, 15),
    ("班会：思政主题教育", "每月思想政治主题班会教育", "class_meeting", "medium", 1, 19),
    ("班会：安全教育", "防诈骗、消防安全、交通安全等主题教育", "class_meeting", "high", 3, 19),
    ("宿舍走访值班", "晚间宿舍走访，了解学生生活学习状态", "duty", "medium", 0, 21),
    ("宿舍走访值班", "晚间宿舍走访", "duty", "medium", 2, 21),
    ("宿舍走访值班", "晚间宿舍走访", "duty", "medium", 4, 21),
    ("审批学生请假申请", "处理本周学生请假条", "document", "medium", 0, 10),
    ("提交学生思想动态报告", "向学生处提交月度学生思想动态", "report", "high", 4, 17),
    ("心理健康周报上报", "汇总本周重点关注学生情况上报学院", "report", "high", 4, 16),
    ("高风险学生家长沟通", "与高风险学生家长电话沟通近期状况", "follow_up", "high", 3, 10),
]

# ═══════════════════════════════════════════════════════════
#  4. 开始执行
# ═══════════════════════════════════════════════════════════
print("=" * 70)
print("  聆心 v3.2 — 确定性种子数据生成（每辅导员 50 名学生）")
print("=" * 70)

# --- 4a. 清理旧数据 ---
with db.get_session() as session:
    session.query(Todo).delete()
    session.query(Reminder).delete()
    session.query(EmotionLog).delete()
    session.query(AlertLog).delete()
    session.query(EmotionTracker).delete()
    session.query(Message).delete()
    session.query(Appointment).delete()
    session.query(StudentProfile).delete()
    session.query(AssessmentResult).delete()
    session.query(ConversationRecord).delete()
    session.query(SystemLog).delete()
    # 清理历史遗留的无用账号（zhangsan/lisi/wangwu/xuegong01/xuegong02）
    for uname in STRAY_USERNAMES:
        user = session.query(User).filter(User.username == uname).first()
        if user is not None:
            session.query(Student).filter(Student.counselor_id == user.id).update({"counselor_id": None})
            session.delete(user)
    session.query(Student).delete()
    session.commit()
    print("\n[1/5] 已清空旧数据（学生/提醒/待办/情绪/预警/消息/遗留账号）")

# --- 4b. 创建/更新账号（学工处 + 辅导员） ---
counselor_map = {}  # username -> user_id
with db.get_session() as session:
    # 学工处 / 管理员
    for uname, pwd, display, role, college in STAFF_ACCOUNTS:
        existing = session.query(User).filter(User.username == uname).first()
        if existing:
            existing.password_hash = generate_password_hash(pwd)
            existing.display_name = display
            existing.role = role
            existing.college = college
            existing.is_active = True
            uid = existing.id
        else:
            u = User(username=uname, password_hash=generate_password_hash(pwd),
                     display_name=display, role=role, college=college, is_active=True)
            session.add(u)
            session.flush()
            uid = u.id
        print(f"  [账号] id={uid} [{role}] {display} ({uname}) — {college}")

    # 辅导员
    for uname, pwd, display, college, classes in COLLEGE_COUNSELORS:
        existing = session.query(User).filter(User.username == uname).first()
        if existing:
            existing.password_hash = generate_password_hash(pwd)
            existing.display_name = display
            existing.college = college
            existing.role = "counselor"
            existing.is_active = True
            uid = existing.id
            action = "更新"
        else:
            u = User(username=uname, password_hash=generate_password_hash(pwd),
                     display_name=display, college=college, role="counselor", is_active=True)
            session.add(u)
            session.flush()
            uid = u.id
            action = "新建"
        counselor_map[uname] = uid
        print(f"  [{action}] id={uid} [counselor] {display} ({uname}) — {college} · {len(classes)}个班")

    session.commit()

print(f"\n[2/5] 账号创建完成：学工处/管理员 {len(STAFF_ACCOUNTS)} 人 + 辅导员 {len(counselor_map)} 人")

# --- 4c. 创建学生（每辅导员固定 50 名） ---
counselor_classes = {}
for uname, pwd, display, college, classes in COLLEGE_COUNSELORS:
    uid = counselor_map[uname]
    counselor_classes[uid] = [(cls, college) for cls in classes]

all_students = []
student_id_counter = 0  # 全局计数器确保学号唯一

for uid, class_list in counselor_classes.items():
    num_classes = len(class_list)
    base = TOTAL_STUDENTS_PER_COUNSELOR // num_classes
    rem = TOTAL_STUDENTS_PER_COUNSELOR % num_classes
    for ci, (cls_name, college) in enumerate(class_list):
        grade = cls_name[:4]
        num = base + (1 if ci < rem else 0)
        for i in range(num):
            student_id_counter += 1
            student_id_val = f"{grade}{student_id_counter:04d}"  # 如: 20240001

            # 确定性性别/姓名：按全局序号交替，保证同名不同班、完全可复现
            gender = "男" if student_id_counter % 2 == 0 else "女"
            pool = MALE_NAMES if gender == "男" else FEMALE_NAMES
            name = pool[(student_id_counter // 2) % len(pool)]

            # 情绪和风险（固定种子，可复现）
            emotion = random.choices(EMOTIONS, weights=EMOTION_WEIGHTS, k=1)[0]
            risk = random.choice(RISK_LEVELS_WEIGHTED)
            if risk == "high":
                emotion = random.choice(["焦虑", "压抑", "恐惧", "悲伤", "低落", "紧张"])
            elif risk == "medium":
                emotion = random.choice(["低落", "焦虑", "烦躁", "紧张", "正常", "正常"])

            notes = random.choice(NOTES_POOL) if random.random() > 0.4 else ""

            all_students.append({
                "student_id": student_id_val,
                "name": name,
                "gender": gender,
                "college": college,
                "class_name": cls_name,
                "counselor_id": uid,
                "risk_level": risk,
                "emotion_status": emotion,
                "notes": notes,
                "phone": f"1{random.choice(['38','39','58','59','50','51','52','55'])}{random.randint(10000000,99999999)}",
            })

created_students = []
with db.get_session() as session:
    for s in all_students:
        st = Student(
            student_id=s["student_id"],
            name=s["name"],
            password_hash=generate_password_hash(STUDENT_DEFAULT_PASSWORD),
            gender=s["gender"],
            college=s["college"],
            class_name=s["class_name"],
            phone=s["phone"],
            counselor_id=s["counselor_id"],
            risk_level=s["risk_level"],
            emotion_status=s["emotion_status"],
            notes=s["notes"],
            is_active=True,
            created_at=now - timedelta(days=random.randint(1, 365)),
            updated_at=now,
        )
        session.add(st)
        session.flush()
        created_students.append({"db_id": st.id, **s})
    session.commit()

print(f"\n[3/5] 学生数据创建完成，共 {len(created_students)} 人")

# 统计各辅导员学生数
counselor_student_count = {}
for s in created_students:
    counselor_student_count[s["counselor_id"]] = counselor_student_count.get(s["counselor_id"], 0) + 1
for uname, uid in counselor_map.items():
    cnt = counselor_student_count.get(uid, 0)
    print(f"    {uname}: {cnt} 名学生")

# --- 4d. 创建提醒 (Reminders) ---
high_risk_students = [s for s in created_students if s["risk_level"] == "high"]
medium_risk_students = [s for s in created_students if s["risk_level"] == "medium"]

reminder_count = 0
with db.get_session() as session:
    for uid, class_list in counselor_classes.items():
        for day_offset in range(-3, 14):
            d = today + timedelta(days=day_offset)
            weekday = d.weekday()
            for tmpl in REMINDER_TEMPLATES:
                if tmpl[4] == weekday:
                    session.add(Reminder(
                        student_id=created_students[0]["db_id"],
                        counselor_id=uid,
                        title=tmpl[0],
                        description=tmpl[1],
                        reminder_type=tmpl[2],
                        priority=tmpl[3],
                        due_date=d.replace(hour=tmpl[5], minute=random.choice([0, 30])),
                        is_completed=(d.date() < today.date()),
                    ))
                    reminder_count += 1

        my_high = [s for s in high_risk_students if s["counselor_id"] == uid]
        for day_offset in range(-3, 14):
            d = today + timedelta(days=day_offset)
            if d.weekday() in [0, 2, 4]:
                for s in my_high[:3]:
                    session.add(Reminder(
                        student_id=s["db_id"], counselor_id=uid,
                        title=f"情绪关怀：{s['name']} — 每日谈心",
                        description=f"学生当前情绪为「{s['emotion_status']}」，风险等级高，建议每日关注",
                        reminder_type="emotion_check", priority="high",
                        due_date=d.replace(hour=random.choice([9, 14, 16]), minute=0),
                        is_completed=(d.date() < today.date()),
                    ))
                    reminder_count += 1

        my_medium = [s for s in medium_risk_students if s["counselor_id"] == uid]
        for day_offset in range(0, 14, 7):
            d = today + timedelta(days=day_offset)
            for s in my_medium[:5]:
                session.add(Reminder(
                    student_id=s["db_id"], counselor_id=uid,
                    title=f"周度跟进：{s['name']}",
                    description="中风险学生，本周安排一次谈心谈话",
                    reminder_type="emotion_check", priority="medium",
                    due_date=d.replace(hour=random.choice([10, 15]), minute=0),
                    is_completed=(d.date() < today.date()),
                ))
                reminder_count += 1
    session.commit()

print(f"\n[4/5] 工作台提醒数据创建完成，共 {reminder_count} 条")

# --- 4e. 创建待办 (Todos) ---
todo_count = 0
with db.get_session() as session:
    for uid in counselor_classes.keys():
        for day_offset in range(-3, 7):
            d = today + timedelta(days=day_offset)
            num_todos = random.randint(1, 3)
            for _ in range(num_todos):
                cat = random.choice(["student_care", "student_care", "work_task", "work_task", "other"])
                if cat == "student_care":
                    titles = ["跟进学生学业情况", "查看学生心理评估报告", "回复学生咨询",
                             "安排谈心谈话", "学生档案更新", "重点关注学生回访", "宿舍纠纷调解"]
                    descs = ["需在本周内完成", "及时了解学生动态", "做好记录"]
                elif cat == "work_task":
                    titles = ["整理谈心记录", "提交周报", "准备班会材料", "学风建设方案撰写",
                             "困难学生家访计划", "就业指导材料准备", "助学金评审材料"]
                    descs = ["按学院要求完成", "按时提交", ""]
                else:
                    titles = ["参加培训课程", "阅读学生管理文献", "更新个人工作计划",
                             "整理办公文档", "处理学院临时通知"]
                    descs = ["", "", ""]
                pri = random.choice(["high", "medium", "medium", "low"])
                session.add(Todo(
                    user_id=uid,
                    title=random.choice(titles),
                    description=random.choice(descs),
                    category=cat,
                    priority=pri,
                    due_date=d.replace(hour=18, minute=0) if random.random() > 0.3 else None,
                    is_completed=(d.date() < today.date() and random.random() > 0.4),
                ))
                todo_count += 1
    session.commit()

print(f"       待办数据创建完成，共 {todo_count} 条")

# --- 4f. 创建情绪日志 (EmotionLogs) 和预警 (AlertLogs) ---
emotion_count = 0
alert_count = 0
with db.get_session() as session:
    for s in created_students:
        uid = s["counselor_id"]
        num_logs = DEMO_EMOTION_LOGS_PER_STUDENT + (1 if s["risk_level"] == "high" else 0)
        for _ in range(num_logs):
            days_ago = random.randint(0, 30)
            log_time = now - timedelta(days=days_ago, hours=random.randint(0, 12))
            emotion = random.choices(EMOTIONS, weights=EMOTION_WEIGHTS, k=1)[0]
            conf = round(random.uniform(0.55, 0.98), 2)
            intensity = random.randint(1, 10)

            if emotion in ["焦虑", "压抑", "恐惧", "悲伤"] and intensity >= 7:
                risk = "high"
            elif intensity >= 5:
                risk = "medium"
            elif emotion in ["低落", "烦躁", "紧张"] and intensity >= 6:
                risk = "medium"
            else:
                risk = "low"

            session.add(EmotionLog(
                student_name=s["name"],
                student_class=s["class_name"],
                emotion=emotion,
                confidence=conf,
                intensity=intensity,
                risk_level=risk,
                analyzed_by=uid,
                created_at=log_time,
            ))
            emotion_count += 1

            if risk == "high":
                session.add(AlertLog(
                    student_name=s["name"],
                    student_class=s["class_name"],
                    risk_level=risk,
                    emotion_type=emotion,
                    intensity=intensity,
                    description=f"学生 {s['name']} 情绪「{emotion}」强度 {intensity}，建议立即关注",
                    status=random.choice(["pending", "pending", "pending", "acknowledged"]),
                    assigned_to=uid,
                    created_at=log_time,
                ))
                alert_count += 1
    session.commit()

print(f"       情绪日志创建完成，共 {emotion_count} 条")
print(f"       预警记录创建完成，共 {alert_count} 条")

# --- 4g. 创建师生对话消息 (Messages) ---
msg_count = 0
conversations = [
    # 学业压力类
    ("老师，最近专业课好难，感觉跟不上进度了", "别着急，大一上学期适应期很正常。我帮你联系了学习委员，可以建个学习小组", "谢谢老师！我今晚就去图书馆找他们一起复习"),
    ("老师，高数期中考试我可能挂科了，好焦虑", "先别慌，等成绩出来再说。就算不理想，还有补考机会，我帮你找高数老师聊聊重点", "嗯嗯，我会好好复习的"),
    ("老师，我想转专业去计算机学院，需要什么条件", "转专业需要大一学年成绩排名前30%，而且要通过目标学院的面试。你先稳住现在的成绩", "好的，我会努力的！"),
    # 人际关系类
    ("老师，我和室友闹矛盾了，他们总是不打扫卫生", "宿舍生活需要互相体谅。我先和你们寝室长聊聊，你们也可以开个寝室会议定个值日表", "好的，其实我也想和他们好好相处的"),
    ("老师，我感觉班上的同学都不太理我，很孤独", "大一刚来都这样，多参加社团活动慢慢就熟了。下周的班级团建你一定要来啊", "好，我会去的，谢谢老师鼓励"),
    ("老师，我和异地恋的女朋友吵架了，心情很差", "感情的事需要双方理解。不过期末了，先把注意力放学习上，考完试再好好沟通", "您说得对，我先专心复习吧"),
    # 经济困难类
    ("老师，我家最近出了点状况，能不能申请临时困难补助", "你把情况写个说明，我帮你提交到学工办。学校有应急基金，别因为钱的事耽误学习", "谢谢老师，我这就去准备材料"),
    ("老师，勤工俭学的岗位还有吗，我想减轻家里负担", "图书馆和食堂还有空缺，时薪不高但能覆盖生活费。我帮你登记一下", "太好了，我可以利用课余时间去"),
    # 就业发展类
    ("老师，马上要毕业了，考研还是工作我很纠结", "这个要结合你的专业和兴趣。如果对本专业有热情建议考研，想早点独立就工作。这周来找我详细聊聊", "好的老师，我整理一下自己的思路再找您"),
    ("老师，暑假实习怎么找啊，我完全没有头绪", "学校就业网有很多实习信息，5月份还有专场招聘会。你先把简历做好发给我看看", "谢谢老师，我这两天就做简历"),
    # 身心健康类
    ("老师，我最近总是失眠到凌晨三四点，白天浑浑噩噩的", "睡眠问题要重视。你先试试睡前不玩手机、喝杯热牛奶。如果持续两周没改善，我陪你去校医院看看", "好的，我今晚就开始试试"),
    ("老师，我感觉做什么都提不起兴趣，是不是抑郁了", "能主动说出来已经很勇敢了。学校心理中心有专业咨询师，完全保密。我帮你预约明天的时段？", "嗯...好吧，我试试"),
    # 校园生活类
    ("老师，我想组织班级春游，需要走什么流程", "先做一份活动方案和安全预案，我帮你提交学院审批。记得给每个同学买保险", "好的！我已经在做方案了，做好就发给您"),
    ("老师，我的校园卡丢了怎么办", "先去一卡通中心挂失，然后带上学生证去补办。期间可以用手机支付过渡一下", "谢谢老师，我马上去办"),
    ("老师，图书馆占座现象太严重了，能不能反映一下", "这个问题很多同学反映过，图书馆已经在推行座位预约系统了。你们也可以联名写个建议书", "好主意！我联合几个同学一起写"),
    # 特殊情景类
    ("老师，我想休学一年去创业，您觉得可以吗", "创业想法很好，但建议先完成学业。可以利用寒暑假先试试水，毕业后再全力投入也不迟", "您说得有道理，我再考虑考虑"),
    ("老师，我被诈骗了2000块钱，现在不知道怎么办", "先别急，保留好转账记录和聊天截图，我陪你去保卫处报案。以后陌生链接千万别点", "谢谢老师，我已经把所有记录截图了"),
    ("老师，我爸妈最近闹离婚，我完全没法专心学习", "家庭变故确实很难受。这段时间你可以随时来找我聊，学习上我会和各科老师打招呼", "老师您真好...我会调整好状态的"),
    ("老师，我想报名参军，您支持吗", "参军报国是光荣的事！大二结束去刚好，保留学籍两年。我帮你联系武装部了解政策", "谢谢老师支持！我一直有这个梦想"),
    ("老师，我被选上参加全国大学生英语竞赛了", "太棒了！这是很好的锻炼机会。学院会安排指导老师帮你备赛，争取拿个好名次", "我会加油的！"),
]
with db.get_session() as session:
    for s in created_students:
        uid = s["counselor_id"]
        has_chat = s["risk_level"] == "high" or random.random() < 0.85  # 85%学生有聊天
        if not has_chat:
            continue
        conv = random.choice(conversations)
        days_ago = random.randint(1, 21)
        base_time = now - timedelta(days=days_ago, hours=random.randint(8, 18))

        msgs = [
            (conv[0], "student"),
            (conv[1], "counselor"),
            (conv[2], "student"),
        ]
        extra_replies = [
            ("好的，那就这样，有什么问题随时联系我", "counselor"),
            ("嗯嗯，我会照做的，谢谢老师", "student"),
            ("保持好心态，一切都会好起来的 💪", "counselor"),
            ("老师您太暖心了，真的很感谢您", "student"),
            ("记得按时完成，有问题随时找我", "counselor"),
            ("收到！老师辛苦了 🌹", "student"),
        ]
        for _ in range(random.randint(1, 2)):
            msgs.append(random.choice(extra_replies))

        for i, (content, sender_type) in enumerate(msgs):
            session.add(Message(
                student_id=s["db_id"], counselor_id=uid,
                sender_type=sender_type,
                sender_id=s["db_id"] if sender_type == "student" else uid,
                content=content, message_type="text",
                is_read=(i < len(msgs) - 1 or random.random() > 0.3),
                created_at=base_time + timedelta(minutes=random.randint(i * 5, i * 30 + 10))
            ))
            msg_count += 1
    session.commit()

print(f"       师生消息创建完成，共 {msg_count} 条")

# ═══════════════════════════════════════════════════════════
#  5. 输出测试账号
# ═══════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("  📋 测试账号汇总")
print("=" * 70)

print("\n  【超级管理员】")
print("    admin / admin123")
print("\n  【学工处】")
print("    liuxin / staff123  (刘鑫)")
print("    student_affairs / staff123  (学工处管理员)")
print("\n  【辅导员/老师】(密码均为 counsel123)")
for uname, pwd, display, college, classes in COLLEGE_COUNSELORS:
    uid = counselor_map.get(uname, "?")
    cnt = counselor_student_count.get(uid, 0)
    print(f"    {uname} / {pwd}  ({display} — {college} · {cnt}名学生)")

print("\n  【学生账号】(密码均为 123456，各辅导员前 3 名学生示例)")
for uname, pwd, display, college, classes in COLLEGE_COUNSELORS:
    uid = counselor_map.get(uname)
    my_students = [s for s in created_students if s["counselor_id"] == uid]
    for s in my_students[:3]:
        print(f"    {s['student_id']} / 123456  ({s['name']} — {s['class_name']} · 辅导员:{display})")

print("\n  【数据统计】")
print(f"    辅导员/老师: {len(COLLEGE_COUNSELORS)} 人")
print(f"    学工处管理员: {len([a for a in STAFF_ACCOUNTS if a[3] == 'student_affairs'])} 人")
print(f"    学生总数: {len(created_students)} 人")
print(f"    高风险学生: {len(high_risk_students)} 人")
print(f"    中风险学生: {len(medium_risk_students)} 人")
print(f"    工作台提醒: {reminder_count} 条")
print(f"    待办事项: {todo_count} 条")
print(f"    情绪日志: {emotion_count} 条")
print(f"    预警记录: {alert_count} 条")
print(f"    师生消息: {msg_count} 条")
print("\n" + "=" * 70)
print("  ✅ 种子数据创建完成！运行 python app.py 启动")
print("=" * 70)
