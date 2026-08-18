import sys, os, json, random
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from core.database import DatabaseManager, AuthManager, User, ConversationRecord, EmotionLog, AlertLog
from sqlalchemy.orm import Session

db = DatabaseManager()

# ============================================================
# 1. 创建额外用户（辅导员和学工处）
# ============================================================
extra_users = [
    ("zhangsan", "123456", "counselor", "张老师", "计算机学院", "13800001001"),
    ("lisi", "123456", "counselor", "李老师", "机械工程学院", "13800001002"),
    ("wangwu", "123456", "counselor", "王老师", "外国语学院", "13800001003"),
    ("student_affairs", "123456", "student_affairs", "学工处管理员", "学生工作处", "13800001010"),
]

auth = AuthManager(db)
for uname, pwd, role, display, college, phone in extra_users:
    try:
        auth.create_user(uname, pwd, role, display, college)
        print(f"  Created user: {display}")
    except:
        print(f"  User {uname} exists, skip")

# ============================================================
# 2. 模拟谈心谈话记录
# ============================================================
conversations = [
    {
        "counselor_id": 2, "student_name": "王小明", "student_class": "计算机学院2023级1班",
        "topic": "学业压力与家庭困难",
        "content": "辅导员：小明，最近期中考试成绩出来了，你有几门课不太理想，能聊聊吗？\n学生：老师，最近压力比较大，我爸上个月失业了，我一边打工一边上课，实在顾不过来。\n辅导员：理解你的情况，学校有助学金和勤工俭学岗位，我帮你申请。\n学生：谢谢老师，我真的很需要。\n辅导员：别担心，先把家里情况稳定下来，学业上的事我们一起想办法。",
        "structured_content": "## 谈心谈话记录\n\n| 项目 | 内容 |\n|------|------|\n| **时间** | 2026年3月15日 14:30 |\n| **地点** | 计算机学院辅导员办公室 |\n| **谈话人** | 张老师 |\n| **谈话对象** | 王小明（计算机学院2023级1班） |\n| **谈话主题** | 学业压力与家庭经济困难 |\n\n### 一、谈话背景\n学生期中考试成绩不理想，辅导员主动约谈了解情况。\n\n### 二、谈话主要内容\n1. 学生反映父亲近期失业，家庭经济压力大\n2. 学生边打工边上课，精力不足\n3. 辅导员介绍助学金和勤工俭学政策\n\n### 三、学生思想与情绪状态评估\n学生情绪低落但态度积极，愿意接受帮助，无极端情绪。\n\n### 四、发现的主要问题\n- 家庭经济困难，需要资助支持\n- 学业成绩下滑，需要学业辅导\n\n### 五、后续跟进措施\n- 3月20日前协助申请助学金\n- 联系任课老师说明情况，争取补考机会\n- 安排勤工俭学岗位",
        "emotion_tags": {"primary": "焦虑", "secondary": "低落", "intensity": 6},
        "risk_level": "medium", "status": "completed"
    },
    {
        "counselor_id": 2, "student_name": "李小红", "student_class": "计算机学院2024级2班",
        "topic": "宿舍人际关系",
        "content": "辅导员：小红，听室友反映你最近和大家相处有些矛盾？\n学生：老师，我觉得她们总是针对我，晚上不关灯、大声说话。\n辅导员：有没有尝试沟通过？\n学生：说了几次，但没什么效果，我现在不太想回宿舍。\n辅导员：我理解你的感受，我来协调一下，也建议你参加宿舍团建活动。",
        "structured_content": "## 谈心谈话记录\n\n| 项目 | 内容 |\n|------|------|\n| **时间** | 2026年3月20日 10:00 |\n| **地点** | 计算机学院谈心室 |\n| **谈话人** | 张老师 |\n| **谈话对象** | 李小红（计算机学院2024级2班） |\n| **谈话主题** | 宿舍人际关系矛盾 |\n\n### 一、谈话背景\n室友反映与该生存在生活习惯冲突，辅导员主动约谈。\n\n### 二、谈话主要内容\n1. 学生反映室友作息习惯影响自己休息\n2. 沟通多次未果，产生回避心理\n3. 辅导员提出协调方案\n\n### 三、学生思想与情绪状态评估\n学生有一定抵触情绪，但愿意配合调解。\n\n### 四、发现的主要问题\n- 宿舍生活习惯差异导致矛盾\n- 沟通方式需要改进\n\n### 五、后续跟进措施\n- 3月22日组织宿舍沟通会\n- 安排参加宿舍团建活动\n- 一周后回访了解进展",
        "emotion_tags": {"primary": "烦躁", "secondary": "压抑", "intensity": 5},
        "risk_level": "low", "status": "completed"
    },
    {
        "counselor_id": 3, "student_name": "赵天宇", "student_class": "机械工程学院2023级3班",
        "topic": "就业焦虑",
        "content": "辅导员：天宇，大三了就业方向考虑得怎么样？\n学生：老师，我很迷茫，投了好多简历都没回音，室友们都有offer了。\n辅导员：找工作是个过程，不要着急。你的专业方向是什么？\n学生：机械设计，但我其实更想做产品经理。\n辅导员：那我们可以帮你做职业规划，也可以参加学校的转行培训。\n学生：真的吗？那太好了。",
        "structured_content": "## 谈心谈话记录\n\n| 项目 | 内容 |\n|------|------|\n| **时间** | 2026年4月2日 15:00 |\n| **地点** | 机械工程学院办公室 |\n| **谈话人** | 李老师 |\n| **谈话对象** | 赵天宇（机械工程学院2023级3班） |\n| **谈话主题** | 就业方向与职业规划 |\n\n### 一、谈话背景\n大三学生就业压力大，主动向辅导员寻求帮助。\n\n### 二、谈话主要内容\n1. 学生反映求职屡屡受挫，产生焦虑\n2. 专业与职业方向不一致\n3. 辅导员提供职业规划资源\n\n### 三、学生思想与情绪状态评估\n学生焦虑但有上进心，目标明确需要引导。\n\n### 四、发现的主要问题\n- 就业方向不明确，需要职业规划指导\n- 求职技巧需要提升\n\n### 五、后续跟进措施\n- 安排学校职业规划咨询\n- 推荐参加产品管理转行培训\n- 两周后跟进求职进展",
        "emotion_tags": {"primary": "焦虑", "secondary": "紧张", "intensity": 7},
        "risk_level": "medium", "status": "completed"
    },
    {
        "counselor_id": 4, "student_name": "陈思雨", "student_class": "外国语学院2024级1班",
        "topic": "情感困惑",
        "content": "辅导员：思雨，最近上课状态不太好，有什么困扰吗？\n学生：老师，我和男朋友分手了，很难走出来，每天晚上睡不着。\n辅导员：感情的事情确实不容易，给自己一些时间。\n学生：我知道，但总是忍不住想，影响了学习。\n辅导员：建议你去学校心理咨询中心聊聊，他们会提供专业帮助。",
        "structured_content": "## 谈心谈话记录\n\n| 项目 | 内容 |\n|------|------|\n| **时间** | 2026年4月10日 11:00 |\n| **地点** | 外国语学院谈心室 |\n| **谈话人** | 王老师 |\n| **谈话对象** | 陈思雨（外国语学院2024级1班） |\n| **谈话主题** | 情感困扰与学业影响 |\n\n### 一、谈话背景\n学生近期上课注意力不集中，辅导员主动关心。\n\n### 二、谈话主要内容\n1. 学生近期经历分手，情绪低落\n2. 失眠影响日常学习\n3. 辅导员建议寻求专业心理帮助\n\n### 三、学生思想与情绪状态评估\n学生情绪波动明显，有失眠症状，建议关注。\n\n### 四、发现的主要问题\n- 情感创伤导致情绪问题\n- 睡眠质量下降影响学业\n\n### 五、后续跟进措施\n- 推荐预约心理咨询中心\n- 安排朋辈辅导员陪伴\n- 一周后回访情绪状态",
        "emotion_tags": {"primary": "悲伤", "secondary": "低落", "intensity": 7},
        "risk_level": "high", "status": "completed"
    },
    {
        "counselor_id": 2, "student_name": "刘浩然", "student_class": "计算机学院2023级1班",
        "topic": "网络成瘾与旷课",
        "content": "辅导员：浩然，你这个月已经缺课8次了，再这样下去会挂科的。\n学生：老师，我知道错了，最近打游戏停不下来。\n辅导员：游戏可以玩，但要有度。你现在每周花多少时间？\n学生：可能每天六七个小时...晚上经常通宵。\n辅导员：这个习惯很不好，我们制定一个作息计划，逐步减少。",
        "structured_content": "## 谈心谈话记录\n\n| 项目 | 内容 |\n|------|------|\n| **时间** | 2026年4月15日 16:00 |\n| **地点** | 计算机学院辅导员办公室 |\n| **谈话人** | 张老师 |\n| **谈话对象** | 刘浩然（计算机学院2023级1班） |\n| **谈话主题** | 网络成瘾与旷课问题 |\n\n### 一、谈话背景\n学生本月旷课8次，辅导员约谈警告。\n\n### 二、谈话主要内容\n1. 学生承认沉迷网络游戏\n2. 每日游戏时间6-7小时，经常通宵\n3. 辅导员制定作息改善计划\n\n### 三、学生思想与情绪状态评估\n学生有自知之明但自控力不足，需要外部约束。\n\n### 四、发现的主要问题\n- 网络游戏成瘾严重\n- 作息紊乱，影响学业\n\n### 五、后续跟进措施\n- 4月20日前制定个人作息计划\n- 每周向辅导员汇报出勤情况\n- 如持续旷课启动学业预警",
        "emotion_tags": {"primary": "正常", "secondary": "烦躁", "intensity": 3},
        "risk_level": "medium", "status": "completed"
    },
    {
        "counselor_id": 3, "student_name": "孙悦", "student_class": "机械工程学院2024级2班",
        "topic": "考研压力",
        "content": "辅导员：小悦，看你最近经常在图书馆待到很晚，考研准备得怎么样？\n学生：老师，压力好大，感觉复习不完，每天都很焦虑。\n辅导员：考研是个长期战，要学会劳逸结合。你报的什么学校？\n学生：想考本校研究生，但竞争很激烈。\n辅导员：本校有优势，导师也比较了解你，我帮你联系一下导师。\n学生：谢谢老师，这对我帮助很大。",
        "structured_content": "## 谈心谈话记录\n\n| 项目 | 内容 |\n|------|------|\n| **时间** | 2026年4月18日 17:30 |\n| **地点** | 机械工程学院办公室 |\n| **谈话人** | 李老师 |\n| **谈话对象** | 孙悦（机械工程学院2024级2班） |\n| **谈话主题** | 考研压力与心理调适 |\n\n### 一、谈话背景\n学生近期学习强度大，辅导员关心其身心状态。\n\n### 二、谈话主要内容\n1. 学生反映考研复习压力大\n2. 目标明确但信心不足\n3. 辅导员提供导师资源对接\n\n### 三、学生思想与情绪状态评估\n学生焦虑但目标坚定，属于正常备考压力。\n\n### 四、发现的主要问题\n- 备考压力大，需要心理疏导\n- 需要学术资源支持\n\n### 五、后续跟进措施\n- 联系目标导师进行学术交流\n- 推荐参加考研经验分享会\n- 两周后跟进备考状态",
        "emotion_tags": {"primary": "焦虑", "secondary": "紧张", "intensity": 6},
        "risk_level": "low", "status": "completed"
    },
]

# ============================================================
# 3. 模拟情绪分析记录
# ============================================================
emotions_data = [
    ("王小明", "计算机学院2023级1班", "焦虑", 3, 0.82, 7, "high"),
    ("李小红", "计算机学院2024级2班", "压抑", 5, 0.78, 6, "medium"),
    ("赵天宇", "机械工程学院2023级3班", "焦虑", 3, 0.85, 7, "high"),
    ("陈思雨", "外国语学院2024级1班", "悲伤", 10, 0.91, 8, "high"),
    ("刘浩然", "计算机学院2023级1班", "正常", 0, 0.88, 2, "none"),
    ("孙悦", "机械工程学院2024级2班", "焦虑", 3, 0.75, 5, "medium"),
    ("周文静", "外国语学院2023级1班", "高兴", 1, 0.90, 2, "none"),
    ("吴志远", "计算机学院2024级1班", "烦躁", 4, 0.73, 6, "medium"),
    ("郑美琪", "机械工程学院2024级1班", "低落", 2, 0.68, 5, "medium"),
    ("黄子轩", "计算机学院2023级2班", "恐惧", 7, 0.80, 7, "high"),
    ("林雅婷", "外国语学院2024级2班", "紧张", 11, 0.77, 6, "medium"),
    ("张伟", "机械工程学院2023级1班", "正常", 0, 0.92, 1, "none"),
]

# ============================================================
# 4. 模拟预警记录
# ============================================================
alerts_data = [
    ("陈思雨", "外国语学院2024级1班", "high", "悲伤", 8, "学生因情感问题出现明显情绪波动，伴有失眠症状，建议启动心理干预流程", "pending"),
    ("黄子轩", "计算机学院2023级2班", "high", "恐惧", 7, "学生语音分析显示持续恐惧情绪，强度较高，建议安排一对一心理辅导", "pending"),
    ("王小明", "计算机学院2023级1班", "high", "焦虑", 7, "家庭经济困难导致焦虑情绪持续，需关注资助落实情况", "acknowledged"),
    ("赵天宇", "机械工程学院2023级3班", "medium", "焦虑", 7, "就业焦虑情绪明显，已安排职业规划咨询", "acknowledged"),
    ("吴志远", "计算机学院2024级1班", "medium", "烦躁", 6, "近期烦躁情绪上升，可能与课业压力有关，持续关注", "pending"),
    ("郑美琪", "机械工程学院2024级1班", "medium", "低落", 5, "情绪持续低落一周，建议安排心理访谈", "resolved"),
    ("李小红", "计算机学院2024级2班", "medium", "压抑", 6, "宿舍矛盾导致压抑情绪，已组织宿舍沟通会", "resolved"),
    ("林雅婷", "外国语学院2024级2班", "medium", "紧张", 6, "考试周紧张情绪升高，推荐参加减压活动", "acknowledged"),
]

with db.get_session() as session:
    # Insert conversations
    now = datetime(2026, 6, 14)
    for i, conv in enumerate(conversations):
        created = now - timedelta(days=random.randint(1, 90), hours=random.randint(8, 18))
        record = ConversationRecord(
            counselor_id=conv["counselor_id"],
            student_name=conv["student_name"],
            student_class=conv["student_class"],
            topic=conv["topic"],
            content=conv["content"],
            structured_content=conv["structured_content"],
            emotion_tags=json.dumps(conv["emotion_tags"], ensure_ascii=False),
            risk_level=conv["risk_level"],
            status=conv["status"],
            created_at=created,
            updated_at=created + timedelta(hours=random.randint(1, 3)),
        )
        session.add(record)
    print(f"  Inserted {len(conversations)} conversation records")

    # Insert emotion logs
    for i, (name, cls, emo, emo_id, conf, intensity, risk) in enumerate(emotions_data):
        created = now - timedelta(days=random.randint(1, 60), hours=random.randint(8, 18))
        log = EmotionLog(
            student_name=name,
            student_class=cls,
            audio_path=f"audio_samples/{name}_sample.wav",
            emotion=emo,
            emotion_id=emo_id,
            confidence=conf,
            intensity=intensity,
            risk_level=risk,
            analyzed_by=random.choice([2, 3, 4]),
            created_at=created,
        )
        session.add(log)
    print(f"  Inserted {len(emotions_data)} emotion logs")

    # Insert alerts
    for name, cls, risk, emo, intensity, desc, status in alerts_data:
        created = now - timedelta(days=random.randint(1, 30), hours=random.randint(8, 18))
        resolved = (now - timedelta(days=random.randint(1, 5))) if status == "resolved" else None
        alert = AlertLog(
            student_name=name,
            student_class=cls,
            risk_level=risk,
            emotion_type=emo,
            intensity=intensity,
            description=desc,
            status=status,
            assigned_to=random.choice([2, 3, 4]),
            created_at=created,
            resolved_at=resolved,
        )
        session.add(alert)
    print(f"  Inserted {len(alerts_data)} alert records")

    session.commit()

print("\nAll mock data inserted successfully!")
