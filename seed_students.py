import sys, os, random
from datetime import datetime, timedelta

os.chdir(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, '.')

from core.database import DatabaseManager, Student

db = DatabaseManager()

surnames = list("王李张刘陈杨赵黄周吴徐孙胡朱高林何郭马罗梁宋郑谢韩唐冯于董萧程曹袁邓许傅沈曾彭吕苏卢蒋蔡贾丁魏薛叶阎余潘杜戴夏钟汪田任姜范方石姚谭廖邹熊金陆郝孔白崔康毛邱秦江史顾侯邵孟龙万段雷钱汤尹黎易常武乔贺赖龚文")
given_names_male = ["伟", "强", "磊", "军", "勇", "杰", "涛", "明", "超", "华", "飞", "鹏", "刚", "辉", "斌", "波", "宁", "浩", "亮", "健", "志", "凯", "毅", "博", "翔", "宇", "泽", "轩", "睿", "辰", "铭", "晨", "旭", "阳", "凯"]
given_names_female = ["芳", "娜", "静", "敏", "丽", "艳", "娟", "玲", "霞", "秀英", "梅", "莉", "婷", "慧", "晶", "琳", "雪", "颖", "佳", "欣", "莹", "瑶", "薇", "思", "怡", "馨", "悦", "宁", "涵", "琪", "乐", "萌", "彤", "雯", "萱"]

colleges = ["计算机学院", "机械工程学院", "外国语学院", "经济管理学院", "电子工程学院", "文学院", "理学院", "化工学院", "土木工程学院", "艺术设计学院"]
grades = ["2022级", "2023级", "2024级"]
class_nums = ["1班", "2班", "3班", "4班", "5班"]

emotions = ["正常", "高兴", "低落", "焦虑", "烦躁", "压抑", "愤怒", "恐惧", "惊讶", "悲伤", "紧张"]
emotion_weights = [30, 20, 10, 10, 8, 5, 4, 3, 3, 4, 3]
risk_levels = ["low", "low", "low", "low", "medium", "medium", "high"]

notes_pool = [
    "", "", "", "", "",
    "该生近期学业压力较大，需关注",
    "性格内向，建议多参加集体活动",
    "家庭经济困难，已申请助学金",
    "体育特长生，训练与学业需平衡",
    "担任班干部，工作积极",
    "入党积极分子，思想进步",
    "近期有挂科风险，需学业辅导",
    "宿舍关系融洽，心理状态良好",
    "转专业学生，适应期需关注",
    "毕业生，就业压力需疏导",
]

# 先清空旧数据
with db.get_session() as session:
    session.query(Student).delete()
    session.commit()
    print("  已清空旧学生数据")

# 生成100个学生
students = []
for i in range(100):
    gender = random.choice(["男", "女"])
    surname = random.choice(surnames)
    given = random.choice(given_names_male if gender == "男" else given_names_female)
    name = surname + given

    grade = random.choice(grades)
    year_prefix = grade[:4]
    seq = f"{i+1:04d}"
    student_id = f"{year_prefix}{seq}"

    college = random.choice(colleges)
    class_name = f"{grade}{random.choice(class_nums)}"
    phone = f"1{random.choice(['38','39','58','59','50','51','52','55','56','57'])}{random.randint(10000000,99999999)}"
    emotion = random.choices(emotions, weights=emotion_weights, k=1)[0]
    risk = random.choice(risk_levels)
    note = random.choice(notes_pool)

    students.append({
        "student_id": student_id,
        "name": name,
        "gender": gender,
        "college": college,
        "class_name": class_name,
        "phone": phone,
        "risk_level": risk,
        "emotion_status": emotion,
        "notes": note,
    })

# 插入数据库
now = datetime.now()
with db.get_session() as session:
    for s in students:
        student = Student(
            student_id=s["student_id"],
            name=s["name"],
            gender=s["gender"],
            college=s["college"],
            class_name=s["class_name"],
            phone=s["phone"],
            risk_level=s["risk_level"],
            emotion_status=s["emotion_status"],
            notes=s["notes"],
            is_active=True,
            created_at=now - timedelta(days=random.randint(1, 180)),
            updated_at=now,
        )
        session.add(student)
    session.commit()
    print(f"  成功插入 {len(students)} 个学生")

    # 统计
    total = session.query(Student).count()
    print(f"\n  数据库学生总数: {total}")

    # 显示前10个
    first10 = session.query(Student).order_by(Student.id).limit(10).all()
    print("\n  前10个学生:")
    for s in first10:
        print(f"    {s.student_id} | {s.name} | {s.gender} | {s.college} | {s.class_name} | 风险:{s.risk_level} | 情绪:{s.emotion_status}")

print("\n  种子数据创建完成!")
