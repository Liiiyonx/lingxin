# -*- coding: utf-8 -*-
"""为师生对话页面生成初始聊天记录"""
import sys, os, random
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from core.database import DatabaseManager, Message

db = DatabaseManager()

conversations = [
    # (student_id, counselor_id, sender_type, sender_id, content, days_ago)
    # 王小明(101) ↔ 张伟(2)
    (101, 2, "student", 101, "老师好，我想问一下助学金申请的事情", 7),
    (101, 2, "counselor", 2, "王小明同学你好，助学金申请需要准备家庭情况证明和申请表，明天可以来办公室取", 7),
    (101, 2, "student", 101, "好的老师，我明天上午去办公室找您", 6),
    (101, 2, "counselor", 2, "没问题，我上午都在。记得带上身份证复印件", 6),
    (101, 2, "student", 101, "谢谢老师！已经拿到表格了", 5),

    # 李思远(102) ↔ 张伟(2)
    (102, 2, "student", 102, "张老师，最近情绪不太好，想找您聊聊", 4),
    (102, 2, "counselor", 2, "思远同学，不用着急。明天上午10点我在谈心室等你，我们好好聊聊", 4),
    (102, 2, "student", 102, "好的老师。最近因为家里出了点事，感觉很压抑", 3),
    (102, 2, "counselor", 2, "家里的事慢慢来，学校这边我会帮你协调。明天先来聊聊，我们一起想办法", 3),
    (102, 2, "student", 102, "谢谢老师关心，那我明天准时到", 2),

    # 赵天宇(106) ↔ 张老师(3)
    (106, 3, "student", 106, "张老师您好，我是计算机2022级2班的赵天宇，想问一下考研的事情", 6),
    (106, 3, "counselor", 3, "天宇你好！考研大三上学期就要开始准备了。你可以先确定目标院校然后制定复习计划", 6),
    (106, 3, "student", 106, "我有点焦虑，感觉大家都开始准备了，我还没头绪", 5),
    (106, 3, "counselor", 3, "别焦虑，现在开始完全来得及。我们学院每年都有考研经验分享会，到时候通知你参加", 5),
    (106, 3, "student", 106, "好的明白了，谢谢老师！", 4),

    # 张雨婷(103) ↔ 李老师(4)
    (103, 4, "student", 103, "李老师好，我是转专业过来的，想了解一下课程安排", 5),
    (103, 4, "counselor", 4, "雨婷同学好！转专业需要补修几门基础课，机械制图确实需要多练习。建议多去实验室动手操作", 5),
    (103, 4, "student", 103, "机械制图好难啊，有没有学习方法推荐？", 4),
    (103, 4, "counselor", 4, "坚持就是胜利。建议多看实物对照图纸理解，有问题随时来问我", 4),
    (103, 4, "student", 103, "太感谢了！我会努力的！", 3),

    # 陈浩然(104) ↔ 王老师(5)
    (104, 5, "student", 104, "王老师好，英语四级考试快到了，好紧张", 3),
    (104, 5, "counselor", 5, "浩然同学别紧张。四级听力关键是平时多练，每天坚持听VOA慢速英语，一个月就会有效果", 3),
    (104, 5, "student", 104, "听力部分总是听不懂怎么办？我做了好几套题了都没进步", 2),
    (104, 5, "counselor", 5, "听力不是刷题就能提升的，要精听！每篇听3遍：第1遍做题、第2遍逐句听懂、第3遍跟读", 2),
    (104, 5, "student", 104, "谢谢老师，我试试精听方法！", 1),
]

def seed():
    print("=" * 60)
    print("生成师生初始聊天记录")
    print("=" * 60)

    now = datetime.now()
    with db.get_session() as session:
        for sid, cid, stype, sender, content, days in conversations:
            t = now - timedelta(days=days, hours=random.randint(8, 18), minutes=random.randint(0, 59))
            is_read = True if stype == "counselor" and days > 1 else False
            msg = Message(
                student_id=sid, counselor_id=cid,
                sender_type=stype, sender_id=sender,
                content=content, message_type="text",
                is_read=is_read, created_at=t,
            )
            session.add(msg)
        session.commit()

    print(f"  [OK] 共生成 {len(conversations)} 条聊天记录")
    print(f"  涉及学生: 王小明、李思远、赵天宇、张雨婷、陈浩然")
    print(f"  涉及老师: 张伟、张老师、李老师、王老师")
    print("=" * 60)

if __name__ == "__main__":
    seed()
