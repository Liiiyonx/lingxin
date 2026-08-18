# -*- coding: utf-8 -*-
"""
数据库模型与操作模块 - 聆心 AI 平台
提供ORM模型定义、数据库管理、用户认证等功能
"""

import os
import sys
from datetime import datetime, timedelta
from contextlib import contextmanager

from sqlalchemy import (
    create_engine, Column, Integer, String, Text, Float, Boolean,
    DateTime, ForeignKey, Enum as SAEnum, JSON, func
)
from sqlalchemy.orm import (
    declarative_base, relationship, sessionmaker, scoped_session
)
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import (
    URLSafeTimedSerializer as Serializer, SignatureExpired, BadSignature
)

# ── 导入配置 ──────────────────────────────────────────────
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from config.config import Config

# ── 基础设置 ──────────────────────────────────────────────
Base = declarative_base()
engine = create_engine(
    Config.SQLALCHEMY_DATABASE_URI,
    echo=Config.SQLALCHEMY_ECHO,
    pool_pre_ping=True,
)
SessionFactory = sessionmaker(bind=engine)
ScopedSession = scoped_session(SessionFactory)


# ===================================================================
#  ORM 模型定义
# ===================================================================

class User(Base):
    """用户表 - 系统管理员、学工人员、辅导员"""
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, index=True)
    password_hash = Column(String(256), nullable=False)
    display_name = Column(String(100), nullable=False)
    role = Column(
        SAEnum("super_admin", "student_affairs", "counselor", name="user_role"),
        nullable=False,
        default="counselor",
    )
    college = Column(String(100), nullable=False, comment="所属学院")
    phone = Column(String(20), default="")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)
    last_login = Column(DateTime, nullable=True)

    # 关系
    conversations = relationship("ConversationRecord", back_populates="counselor")
    alerts = relationship("AlertLog", back_populates="assignee")
    emotion_logs = relationship("EmotionLog", back_populates="analyzer")
    system_logs = relationship("SystemLog", back_populates="user")

    def __repr__(self):
        return f"<User(id={self.id}, username={self.username}, role={self.role})>"


class ConversationRecord(Base):
    """咨询记录表"""
    __tablename__ = "conversation_records"

    id = Column(Integer, primary_key=True, autoincrement=True)
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True, comment="学生主键外键")
    student_name = Column(String(100), nullable=False)
    student_class = Column(String(100), nullable=False, comment="学生班级")
    topic = Column(String(200), nullable=False, comment="咨询主题")
    content = Column(Text, nullable=False, comment="原始对话内容")
    structured_content = Column(Text, nullable=True, comment="AI整理后的结构化内容")
    emotion_tags = Column(JSON, nullable=True, comment="情绪分析结果JSON")
    risk_level = Column(String(20), default="low", comment="风险等级: low/medium/high/critical")
    status = Column(
        SAEnum("draft", "completed", "reviewed", name="record_status"),
        default="draft",
        nullable=False,
    )
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now, nullable=False)

    # 关系
    counselor = relationship("User", back_populates="conversations")

    def __repr__(self):
        return f"<ConversationRecord(id={self.id}, student={self.student_name})>"


class EmotionLog(Base):
    """情绪日志表 - 记录每次语音情绪分析结果"""
    __tablename__ = "emotion_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True, comment="学生主键外键")
    student_name = Column(String(100), nullable=False, index=True)
    student_class = Column(String(100), nullable=False)
    audio_path = Column(String(500), nullable=True, comment="音频文件路径")
    emotion = Column(String(50), nullable=False, comment="情绪类型: happy/sad/anxious/angry/neutral等")
    emotion_id = Column(Integer, nullable=True, comment="情绪编号")
    confidence = Column(Float, nullable=True, comment="置信度 0~1")
    intensity = Column(Integer, nullable=True, comment="情绪强度 1~10")
    risk_level = Column(String(20), default="low")
    analyzed_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # 关系
    analyzer = relationship("User", back_populates="emotion_logs")

    def __repr__(self):
        return f"<EmotionLog(id={self.id}, student={self.student_name}, emotion={self.emotion})>"


class AlertLog(Base):
    """预警日志表"""
    __tablename__ = "alert_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="SET NULL"), nullable=True, index=True, comment="学生主键外键")
    student_name = Column(String(100), nullable=False, index=True)
    student_class = Column(String(100), nullable=False)
    risk_level = Column(String(20), nullable=False, comment="high/critical")
    emotion_type = Column(String(50), nullable=True)
    intensity = Column(Integer, nullable=True)
    description = Column(Text, nullable=True, comment="预警描述")
    status = Column(
        SAEnum("pending", "acknowledged", "resolved", name="alert_status"),
        default="pending",
        nullable=False,
    )
    assigned_to = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)
    resolved_at = Column(DateTime, nullable=True)
    acknowledged_by = Column(Integer, nullable=True, comment="确认人用户ID")
    acknowledged_at = Column(DateTime, nullable=True, comment="确认时间")
    resolved_by = Column(Integer, nullable=True, comment="解决人用户ID")
    resolution = Column(Text, nullable=True, comment="解决备注")

    # 关系
    assignee = relationship("User", back_populates="alerts")

    def __repr__(self):
        return f"<AlertLog(id={self.id}, student={self.student_name}, risk={self.risk_level})>"


class SystemLog(Base):
    """系统操作日志"""
    __tablename__ = "system_logs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    action = Column(String(100), nullable=False, comment="操作类型")
    target_type = Column(String(50), nullable=True, comment="操作对象类型")
    target_id = Column(Integer, nullable=True, comment="操作对象ID")
    details = Column(JSON, nullable=True, comment="操作详情JSON")
    ip_address = Column(String(50), nullable=True)
    created_at = Column(DateTime, default=datetime.now, nullable=False)

    # 关系
    user = relationship("User", back_populates="system_logs")

    def __repr__(self):
        return f"<SystemLog(id={self.id}, action={self.action})>"


class Student(Base):
    """\u5b66\u751f\u4fe1\u606f\u8868 - \u652f\u6301\u5b66\u751f\u767b\u5f55"""
    __tablename__ = "students"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(String(50), unique=True, nullable=False, index=True)
    name = Column(String(100), nullable=False)
    password_hash = Column(String(256), nullable=True, comment="\u5b66\u751f\u767b\u5f55\u5bc6\u7801\u54c8\u5e0c")
    gender = Column(String(10), default="")
    college = Column(String(100), default="")
    class_name = Column(String(100), default="")
    phone = Column(String(20), default="")
    email = Column(String(100), default="", comment="\u5b66\u751f\u90ae\u7bb1")
    avatar = Column(String(500), default="", comment="\u5934\u50cfURL")
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    risk_level = Column(String(20), default="low")
    emotion_status = Column(String(50), default="\u6b63\u5e38")
    notes = Column(Text, default="")
    is_active = Column(Boolean, default=True)
    last_login = Column(DateTime, nullable=True, comment="\u5b66\u751f\u6700\u540e\u767b\u5f55\u65f6\u95f4")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    counselor = relationship("User", foreign_keys=[counselor_id])
    profiles = relationship("StudentProfile", back_populates="student")
    emotion_trackers = relationship("EmotionTracker", back_populates="student")
    reminders = relationship("Reminder", back_populates="student")
    messages = relationship("Message", back_populates="student", foreign_keys="Message.student_id")

    def __repr__(self):
        return f"<Student(id={self.id}, student_id={self.student_id}, name={self.name})>"


class StudentProfile(Base):
    """\u5b66\u751f\u6863\u6848/\u8c08\u5fc3\u8bb0\u5f55\u8868"""
    __tablename__ = "student_profiles"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    record_type = Column(String(50), default="talk")
    summary = Column(Text, nullable=False)
    structured_content = Column(Text, nullable=True)
    emotion_tags = Column(JSON, nullable=True)
    risk_level = Column(String(20), default="low")
    counselor_impression = Column(Text, default="")
    follow_up_needed = Column(Boolean, default=False)
    follow_up_date = Column(DateTime, nullable=True)
    audio_path = Column(String(500), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    student = relationship("Student", back_populates="profiles")
    counselor = relationship("User", foreign_keys=[counselor_id])

    def __repr__(self):
        return f"<StudentProfile(id={self.id}, student_id={self.student_id})>"


class EmotionTracker(Base):
    """\u60c5\u7eea\u8ffd\u8e2a\u8868 - \u5b9a\u671f\u8bb0\u5f55"""
    __tablename__ = "emotion_trackers"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    emotion = Column(String(50), nullable=False)
    intensity = Column(Integer, default=5)
    risk_level = Column(String(20), default="low")
    source = Column(String(50), default="manual")
    notes = Column(Text, default="")
    recorded_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    student = relationship("Student", back_populates="emotion_trackers")
    recorder = relationship("User", foreign_keys=[recorded_by])

    def __repr__(self):
        return f"<EmotionTracker(id={self.id}, emotion={self.emotion})>"


class Reminder(Base):
    """\u63d0\u9192\u8868"""
    __tablename__ = "reminders"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    reminder_type = Column(String(50), default="emotion_check")
    priority = Column(String(20), default="medium")
    due_date = Column(DateTime, nullable=True)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    student = relationship("Student", back_populates="reminders")
    counselor = relationship("User", foreign_keys=[counselor_id])

    def __repr__(self):
        return f"<Reminder(id={self.id}, title={self.title})>"


class Message(Base):
    """\u6d88\u606f\u8868 - \u5b66\u751f\u4e0e\u8f85\u5bfc\u5458\u4e4b\u95f4\u7684\u5373\u65f6\u901a\u8baf"""
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    sender_type = Column(String(20), nullable=False, comment="\u53d1\u9001\u8005\u7c7b\u578b: student/counselor")
    sender_id = Column(Integer, nullable=False, comment="\u53d1\u9001\u8005ID")
    content = Column(Text, nullable=False, comment="\u6d88\u606f\u5185\u5bb9")
    message_type = Column(String(20), default="text", comment="\u6d88\u606f\u7c7b\u578b: text/image/file")
    file_url = Column(String(500), nullable=True, comment="\u6587\u4ef6URL")
    is_read = Column(Boolean, default=False, comment="\u662f\u5426\u5df2\u8bfb")
    created_at = Column(DateTime, default=datetime.now)

    # Relationships
    student = relationship("Student", back_populates="messages")
    counselor = relationship("User", foreign_keys=[counselor_id])

    def __repr__(self):
        return f"<Message(id={self.id}, sender={self.sender_type})>"


class Appointment(Base):
    """\u9884\u7ea6\u8868 - \u5b66\u751f\u9884\u7ea6\u89c6\u9891\u54a8\u8be2"""
    __tablename__ = "appointments"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    counselor_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    appointment_time = Column(DateTime, nullable=False, comment="\u9884\u7ea6\u65f6\u95f4")
    duration = Column(Integer, default=30, comment="\u65f6\u957f(\u5206\u949f)")
    status = Column(String(20), default="pending", comment="\u72b6\u6001: pending/confirmed/completed/cancelled")
    reason = Column(Text, default="", comment="\u9884\u7ea6\u539f\u56e0")
    notes = Column(Text, default="", comment="\u54a8\u8be2\u5907\u6ce8")
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

    # Relationships
    student = relationship("Student", foreign_keys=[student_id])
    counselor = relationship("User", foreign_keys=[counselor_id])

    def __repr__(self):
        return f"<Appointment(id={self.id}, status={self.status})>"


class TokenBlacklist(Base):
    """Token黑名单表 - 存储已注销的Token"""
    __tablename__ = "token_blacklist"

    id = Column(Integer, primary_key=True, autoincrement=True)
    token_jti = Column(String(256), unique=True, nullable=False, index=True, comment="Token唯一标识")
    expires_at = Column(DateTime, nullable=False, comment="Token过期时间")
    revoked_at = Column(DateTime, default=datetime.now, nullable=False)

    def __repr__(self):
        return f"<TokenBlacklist(jti={self.token_jti})>"


class Todo(Base):
    """自定义待办表 - 教师工作台待办事项"""
    __tablename__ = "todos"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True)
    title = Column(String(200), nullable=False)
    description = Column(Text, default="")
    category = Column(String(50), default="work_task", comment="student_care/work_task/other")
    priority = Column(String(20), default="medium", comment="high/medium/low")
    due_date = Column(DateTime, nullable=True)
    is_completed = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

    user = relationship("User", foreign_keys=[user_id])

    def __repr__(self):
        return f"<Todo(id={self.id}, title={self.title})>"


class AssessmentResult(Base):
    """心理测评结果表 - PHQ-9/GAD-7/ISI"""
    __tablename__ = "assessment_results"

    id = Column(Integer, primary_key=True, autoincrement=True)
    student_id = Column(Integer, ForeignKey("students.id", ondelete="CASCADE"), nullable=False, index=True)
    phq9_score = Column(Integer, default=0, comment="PHQ-9总分 0-27")
    phq9_level = Column(String(20), default="none", comment="抑郁等级")
    gad7_score = Column(Integer, default=0, comment="GAD-7总分 0-21")
    gad7_level = Column(String(20), default="none", comment="焦虑等级")
    isi_score = Column(Integer, default=0, comment="ISI总分 0-28")
    isi_level = Column(String(20), default="none", comment="失眠等级")
    item9_score = Column(Integer, default=0, comment="PHQ-9第9题(自伤)得分")
    answers = Column(Text, default="", comment="完整答案JSON")
    duration_seconds = Column(Integer, default=0, comment="答题耗时(秒)")
    created_at = Column(DateTime, default=datetime.now)

    student = relationship("Student", foreign_keys=[student_id])

    def __repr__(self):
        return f"<Assessment(id={self.id}, student={self.student_id}, PHQ9={self.phq9_score})>"


# ===================================================================
#  情绪网络图元信息（图标 / 颜色 / 严重程度）
# ===================================================================

EMOTION_NETWORK_META = {
    "焦虑": {"icon": "😰", "color": "#f59e0b", "severity": 3},
    "悲伤": {"icon": "😢", "color": "#6366f1", "severity": 3},
    "压抑": {"icon": "😞", "color": "#8b5cf6", "severity": 3},
    "恐惧": {"icon": "😨", "color": "#ef4444", "severity": 4},
    "愤怒": {"icon": "😡", "color": "#ef4444", "severity": 4},
    "烦躁": {"icon": "😤", "color": "#f97316", "severity": 2},
    "紧张": {"icon": "😬", "color": "#e67e22", "severity": 2},
    "低落": {"icon": "😔", "color": "#94a3b8", "severity": 2},
    "平静": {"icon": "😌", "color": "#3b82f6", "severity": 0},
    "正常": {"icon": "😐", "color": "#10b981", "severity": 0},
    "高兴": {"icon": "😊", "color": "#10b981", "severity": 0},
    "惊讶": {"icon": "😲", "color": "#f39c12", "severity": 1},
    "厌恶": {"icon": "🤢", "color": "#7f8c8d", "severity": 2},
}

# ===================================================================
#  DatabaseManager - 数据库管理器
# ===================================================================

class DatabaseManager:
    """数据库操作管理器 - 提供统一的会话管理和CRUD操作"""

    def __init__(self):
        self.engine = engine
        self.session_factory = SessionFactory

    # ── 初始化 ────────────────────────────────────────────

    def init_db(self):
        """创建所有表"""
        Base.metadata.create_all(self.engine)
        print("[OK] 数据库表创建完成")

    def migrate_student_id_links(self):
        """为 emotion_logs / alert_logs / conversation_records 补充并回填 student_id 外键（幂等）。

        SQLite 的 create_all 不会给已有表加列，需手动 ALTER + 按姓名回填。
        回填采用内存映射（姓名唯一 → 直接匹配；同名 → 优先同班），避免 SQLite
        相关子查询 ORDER BY 的兼容性问题。新数据写入时自动解析，此方法仅迁移历史数据。
        """
        from sqlalchemy import text
        with self.engine.connect() as conn:
            for table in ("emotion_logs", "alert_logs", "conversation_records"):
                cols = [r[1] for r in conn.execute(text(f"PRAGMA table_info({table})")).fetchall()]
                if "student_id" not in cols:
                    conn.execute(text(f"ALTER TABLE {table} ADD COLUMN student_id INTEGER"))
            conn.commit()

            # 构建 name -> [(id, class_name)] 映射
            name_map = {}
            for sid, sname, sclass in conn.execute(text("SELECT id, name, class_name FROM students")).fetchall():
                name_map.setdefault(sname, []).append((sid, sclass or ""))

            def resolve(row_name, row_class):
                matches = name_map.get(row_name)
                if not matches:
                    return None
                if len(matches) == 1:
                    return matches[0][0]
                for sid, sclass in matches:  # 同名 → 优先同班
                    if sclass == (row_class or ""):
                        return sid
                return None  # 多同名且不同班，无法唯一确定

            for table in ("emotion_logs", "alert_logs", "conversation_records"):
                rows = conn.execute(text(
                    f"SELECT id, student_name, student_class FROM {table} WHERE student_id IS NULL"
                )).fetchall()
                for rid, rname, rclass in rows:
                    sid = resolve(rname, rclass)
                    if sid:
                        conn.execute(text(
                            f"UPDATE {table} SET student_id = :sid WHERE id = :rid"
                        ), {"sid": sid, "rid": rid})
                conn.commit()
        print("[OK] student_id 外键迁移与回填完成")

    def drop_all(self):
        """删除所有表（危险操作）"""
        Base.metadata.drop_all(self.engine)

    # ------------------------------------------------------------------
    # Serialization helper
    # ------------------------------------------------------------------

    @staticmethod
    def _to_dict(obj):
        """Convert an ORM object to a JSON-safe dict."""
        if obj is None:
            return None
        d = {}
        for col in obj.__table__.columns:
            val = getattr(obj, col.name)
            if hasattr(val, 'isoformat'):
                val = str(val)
            d[col.name] = val
        return d

    # ── 会话管理 ──────────────────────────────────────────

    @contextmanager
    def get_session(self):
        """上下文管理器 - 提供自动提交/回滚的数据库会话"""
        session = self.session_factory()
        try:
            yield session
            session.commit()
        except Exception:
            session.rollback()
            raise
        finally:
            session.close()

    @staticmethod
    def _resolve_student_id(session, student_name, student_class=None):
        """根据姓名（优先同班）解析学生主键；无法唯一确定时返回 None。"""
        if not student_name:
            return None
        q = session.query(Student.id).filter(Student.name == student_name)
        if student_class:
            exact = q.filter(Student.class_name == student_class).first()
            if exact:
                return exact[0]
        rows = q.limit(2).all()
        if len(rows) == 1:
            return rows[0][0]
        return None

    # ── User CRUD ─────────────────────────────────────────

    def create_user(self, username, password_hash, display_name, role, college,
                    phone="", is_active=True):
        """创建用户"""
        user = User(
            username=username,
            password_hash=password_hash,
            display_name=display_name,
            role=role,
            college=college,
            phone=phone,
            is_active=is_active,
        )
        with self.get_session() as session:
            session.add(user)
            session.flush()
            return user.id

    def get_user_by_id(self, user_id):
        """根据ID获取用户"""
        with self.get_session() as session:
            return session.query(User).filter(User.id == user_id).first()

    def get_user_by_username(self, username):
        """根据用户名获取用户"""
        with self.get_session() as session:
            user = session.query(User).filter(User.username == username).first()
            if user is None:
                return None
            return {
                "id": user.id,
                "username": user.username,
                "password_hash": user.password_hash,
                "display_name": user.display_name,
                "role": user.role,
                "college": user.college,
                "phone": user.phone,
                "is_active": user.is_active,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "last_login": user.last_login,
            }

    def update_user(self, user_id, **kwargs):
        """更新用户信息"""
        allowed_fields = {
            "display_name", "role", "college", "phone",
            "is_active", "password_hash", "last_login",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False
        updates["updated_at"] = datetime.now()
        with self.get_session() as session:
            rows = session.query(User).filter(User.id == user_id).update(updates)
            return rows > 0

    def delete_user(self, user_id):
        """软删除用户（设置is_active=False）"""
        return self.update_user(user_id, is_active=False)

    def search_users(self, keyword=None, role=None, college=None,
                     page=1, per_page=20):
        """搜索用户 - 支持关键词/角色/学院筛选与分页"""
        with self.get_session() as session:
            query = session.query(User)
            if keyword:
                query = query.filter(
                    User.display_name.contains(keyword)
                    | User.username.contains(keyword)
                )
            if role:
                query = query.filter(User.role == role)
            if college:
                query = query.filter(User.college == college)

            total = query.count()
            items = query.offset((page - 1) * per_page).limit(per_page).all()
            return {"total": total, "page": page, "per_page": per_page, "items": [self._to_dict(i) for i in items]}

    # ── ConversationRecord CRUD ───────────────────────────

    def create_conversation(self, counselor_id, student_name, student_class,
                            topic, content, structured_content=None,
                            emotion_tags=None, risk_level="low", status="draft",
                            student_id=None):
        """创建咨询记录（未显式指定时自动按姓名解析学生主键）"""
        with self.get_session() as session:
            if student_id is None:
                student_id = self._resolve_student_id(session, student_name, student_class)
            record = ConversationRecord(
                counselor_id=counselor_id,
                student_id=student_id,
                student_name=student_name,
                student_class=student_class,
                topic=topic,
                content=content,
                structured_content=structured_content,
                emotion_tags=emotion_tags,
                risk_level=risk_level,
                status=status,
            )
            session.add(record)
            session.flush()
            return record.id

    def get_conversation(self, record_id):
        """获取单条咨询记录"""
        with self.get_session() as session:
            return session.query(ConversationRecord).filter(
                ConversationRecord.id == record_id
            ).first()

    def update_conversation(self, record_id, **kwargs):
        """更新咨询记录"""
        allowed_fields = {
            "structured_content", "emotion_tags", "risk_level", "status", "topic",
        }
        updates = {k: v for k, v in kwargs.items() if k in allowed_fields}
        if not updates:
            return False
        updates["updated_at"] = datetime.now()
        with self.get_session() as session:
            rows = session.query(ConversationRecord).filter(
                ConversationRecord.id == record_id
            ).update(updates)
            return rows > 0

    def delete_conversation(self, conversation_id):
        """删除一条咨询记录"""
        with self.get_session() as session:
            record = session.query(ConversationRecord).filter(
                ConversationRecord.id == conversation_id
            ).first()
            if record is None:
                return False
            session.delete(record)
            return True

    def search_conversations(self, keyword=None, counselor_id=None,
                             risk_level=None, status=None, filters=None, user_id=None, role=None,
                             page=1, per_page=20, **kwargs):
        """搜索咨询记录 — 按角色实施数据隔离"""
        with self.get_session() as session:
            query = session.query(ConversationRecord)
            if keyword:
                query = query.filter(
                    ConversationRecord.student_name.contains(keyword)
                    | ConversationRecord.topic.contains(keyword)
                )
            # 角色数据隔离：辅导员只看自己的记录
            if role == "counselor" and user_id:
                query = query.filter(ConversationRecord.counselor_id == user_id)
            elif counselor_id is not None:
                query = query.filter(ConversationRecord.counselor_id == counselor_id)
            if risk_level:
                query = query.filter(ConversationRecord.risk_level == risk_level)
            if status:
                query = query.filter(ConversationRecord.status == status)

            total = query.count()
            items = query.order_by(ConversationRecord.created_at.desc()) \
                         .offset((page - 1) * per_page).limit(per_page).all()
            return {"total": total, "page": page, "per_page": per_page, "items": [self._to_dict(i) for i in items]}

    # ── EmotionLog CRUD ───────────────────────────────────

    def create_emotion_log(self, student_name, student_class, emotion,
                           emotion_id=None, confidence=None, intensity=None,
                           audio_path=None, risk_level="low", analyzed_by=None,
                           student_id=None):
        """创建情绪日志（未显式指定时自动按姓名解析学生主键）"""
        with self.get_session() as session:
            if student_id is None:
                student_id = self._resolve_student_id(session, student_name, student_class)
            log = EmotionLog(
                student_id=student_id,
                student_name=student_name,
                student_class=student_class,
                emotion=emotion,
                emotion_id=emotion_id,
                confidence=confidence,
                intensity=intensity,
                audio_path=audio_path,
                risk_level=risk_level,
                analyzed_by=analyzed_by,
            )
            session.add(log)
            session.flush()
            return log.id

    def get_emotion_logs(self, student_name=None, emotion=None,
                         risk_level=None, filters=None, page=1, per_page=20, counselor_id=None, **kwargs):
        """查询情绪日志，支持管理员全量查看和辅导员按本人过滤。"""
        with self.get_session() as session:
            query = session.query(EmotionLog)
            filters = filters or {}
            student_name = student_name or filters.get("student_name")
            emotion = emotion or filters.get("emotion")
            risk_level = risk_level or filters.get("risk_level")
            if counselor_id:
                query = query.filter(EmotionLog.analyzed_by == counselor_id)
            if student_name:
                query = query.filter(EmotionLog.student_name.contains(student_name))
            if emotion:
                query = query.filter(EmotionLog.emotion == emotion)
            if risk_level:
                query = query.filter(EmotionLog.risk_level == risk_level)
            date_from = filters.get("date_from")
            date_to = filters.get("date_to")
            if date_from:
                try:
                    query = query.filter(EmotionLog.created_at >= datetime.fromisoformat(str(date_from)))
                except Exception:
                    pass
            if date_to:
                try:
                    query = query.filter(EmotionLog.created_at <= datetime.fromisoformat(str(date_to)))
                except Exception:
                    pass

            total = query.count()
            total_pages = (total + per_page - 1) // per_page if per_page else 0
            items = query.order_by(EmotionLog.created_at.desc(), EmotionLog.id.desc()) \
                         .offset((page - 1) * per_page).limit(per_page).all()
            return {"total": total, "total_pages": total_pages, "page": page, "per_page": per_page, "items": [self._to_dict(i) for i in items]}
    def get_emotion_statistics(self, counselor_id=None, **kwargs):
        """获取情绪统计数据（供情绪看板使用），支持按辅导员过滤"""
        with self.get_session() as session:
            from collections import Counter
            q = session.query(EmotionLog)
            if counselor_id:
                q = q.filter(EmotionLog.analyzed_by == counselor_id)
            logs = q.all()
            if not logs:
                return {"total": 0, "emotion_distribution": {}, "avg_intensity": 0,
                        "high_risk_count": 0, "medium_risk_count": 0, "low_risk_count": 0}
            total = len(logs)
            intensities = [l.intensity for l in logs if l.intensity]
            avg_intensity = round(sum(intensities) / len(intensities), 1) if intensities else 0
            emotion_counts = Counter(l.emotion for l in logs)
            distribution = {emo: {"count": cnt, "percentage": round(cnt/total*100, 1)}
                          for emo, cnt in emotion_counts.most_common()}
            risk_counts = Counter(l.risk_level for l in logs)
            return {"total": total, "emotion_distribution": distribution,
                    "avg_intensity": avg_intensity,
                    "high_risk_count": risk_counts.get("high", 0),
                    "medium_risk_count": risk_counts.get("medium", 0),
                    "low_risk_count": risk_counts.get("low", 0) + risk_counts.get("none", 0)}

    def get_emotion_trends(self, days=7, student_id=None, class_name=None):
        """获取情绪趋势数据（供折线图使用）"""
        with self.get_session() as session:
            from datetime import datetime as _dt, timedelta as _td
            today = _dt.now()
            start = today - _td(days=days)
            logs = session.query(EmotionLog).filter(EmotionLog.created_at >= start).all()
            daily_data = {}
            for i in range(days):
                d = today - _td(days=days-1-i)
                ds = d.strftime("%m-%d")
                daily_data[ds] = {"date": ds, "count": 0, "avg_intensity": 0}
            for l in logs:
                ds = l.created_at.strftime("%m-%d") if l.created_at else ""
                if ds in daily_data:
                    daily_data[ds]["count"] += 1
            for ds in daily_data:
                day_logs = [l for l in logs if l.created_at and l.created_at.strftime("%m-%d") == ds]
                intensities = [l.intensity for l in day_logs if l.intensity]
                daily_data[ds]["avg_intensity"] = round(sum(intensities)/len(intensities),1) if intensities else 0
            return list(daily_data.values())

    def get_emotion_heatmap(self, date_from=None, date_to=None, college=None):
        """获取情绪热力图数据（供热力图使用）"""
        with self.get_session() as session:
            logs = session.query(EmotionLog).all()
            emotions = ["正常","高兴","低落","焦虑","烦躁","压抑","愤怒","恐惧","惊讶","厌恶","悲伤","紧张"]
            intensity_bins = ["0-2","3-4","5-6","7-8","9-10"]
            matrix = [[0]*5 for _ in range(len(emotions))]
            for l in logs:
                if l.emotion in emotions:
                    ei = emotions.index(l.emotion)
                    if l.intensity is None: continue
                    if l.intensity <= 2: bi = 0
                    elif l.intensity <= 4: bi = 1
                    elif l.intensity <= 6: bi = 2
                    elif l.intensity <= 8: bi = 3
                    else: bi = 4
                    matrix[ei][bi] += 1
            return {"matrix": matrix, "emotion_labels": emotions, "intensity_labels": intensity_bins}

    # ── AlertLog CRUD ─────────────────────────────────────

    def create_alert(self, student_name, student_class, risk_level,
                     emotion_type=None, intensity=None, description=None,
                     assigned_to=None, student_id=None):
        """创建预警（未显式指定时自动按姓名解析学生主键）"""
        with self.get_session() as session:
            if student_id is None:
                student_id = self._resolve_student_id(session, student_name, student_class)
            alert = AlertLog(
                student_id=student_id,
                student_name=student_name,
                student_class=student_class,
                risk_level=risk_level,
                emotion_type=emotion_type,
                intensity=intensity,
                description=description,
                assigned_to=assigned_to,
            )
            session.add(alert)
            session.flush()
            return alert.id

    def add_alert_log(self, student_name, student_class="", emotion_type=None,
                      intensity=None, risk_level="medium", details=None, assigned_to=None):
        """新增预警（兼容实时情绪告警调用，details 映射为 description）"""
        return self.create_alert(
            student_name=student_name,
            student_class=student_class,
            risk_level=risk_level,
            emotion_type=emotion_type,
            intensity=intensity,
            description=details,
            assigned_to=assigned_to,
        )

    def update_alert_status(self, alert_id, status, resolved_at=None):
        """更新预警状态"""
        updates = {"status": status}
        if status == "resolved":
            updates["resolved_at"] = resolved_at or datetime.now()
        with self.get_session() as session:
            rows = session.query(AlertLog).filter(AlertLog.id == alert_id).update(updates)
            return rows > 0

    def get_pending_alerts(self, assigned_to=None):
        """获取待处理预警"""
        with self.get_session() as session:
            query = session.query(AlertLog).filter(AlertLog.status == "pending")
            if assigned_to is not None:
                query = query.filter(AlertLog.assigned_to == assigned_to)
            return query.order_by(AlertLog.created_at.desc()).all()

    def search_alerts(self, student_name=None, risk_level=None, status=None,
                      page=1, per_page=20, **kwargs):
        """搜索预警"""
        with self.get_session() as session:
            query = session.query(AlertLog)
            if student_name:
                query = query.filter(AlertLog.student_name.contains(student_name))
            if risk_level:
                query = query.filter(AlertLog.risk_level == risk_level)
            if status:
                query = query.filter(AlertLog.status == status)

            total = query.count()
            items = query.order_by(AlertLog.created_at.desc()) \
                         .offset((page - 1) * per_page).limit(per_page).all()
            return {"total": total, "page": page, "per_page": per_page, "items": [self._to_dict(i) for i in items]}

    def get_alert(self, alert_id):
        """获取单条预警记录（字典）"""
        with self.get_session() as session:
            alert = session.query(AlertLog).filter(AlertLog.id == alert_id).first()
            return self._to_dict(alert) if alert else None

    def update_alert(self, alert_id, updates):
        """更新预警记录（状态/确认人/解决备注等）"""
        allowed_fields = {
            "status", "description", "emotion_type", "intensity",
            "assigned_to", "resolved_at", "acknowledged_by",
            "acknowledged_at", "resolved_by", "resolution",
        }
        mapped = {k: v for k, v in (updates or {}).items() if k in allowed_fields}
        if not mapped:
            return False
        with self.get_session() as session:
            rows = session.query(AlertLog).filter(AlertLog.id == alert_id).update(mapped)
            return rows > 0

    def get_alert_statistics(self, **kwargs):
        """获取预警统计数据，支持日期过滤"""
        from collections import Counter
        with self.get_session() as session:
            query = session.query(AlertLog)
            date_from = kwargs.get("date_from")
            date_to = kwargs.get("date_to")
            if date_from:
                try:
                    query = query.filter(AlertLog.created_at >= datetime.fromisoformat(str(date_from)))
                except Exception:
                    pass
            if date_to:
                try:
                    query = query.filter(AlertLog.created_at <= datetime.fromisoformat(str(date_to)))
                except Exception:
                    pass
            alerts = query.all()
            risk_counts = Counter(a.risk_level for a in alerts)
            status_counts = Counter(a.status for a in alerts)
            return {
                "total": len(alerts),
                "pending": status_counts.get("pending", 0),
                "acknowledged": status_counts.get("acknowledged", 0),
                "resolved": status_counts.get("resolved", 0),
                "risk_distribution": {
                    "high": risk_counts.get("high", 0),
                    "medium": risk_counts.get("medium", 0),
                    "low": risk_counts.get("low", 0),
                },
            }

    # ── SystemLog ─────────────────────────────────────────

    def log_action(self, user_id, action, target_type=None, target_id=None,
                   details=None, ip_address=None):
        """记录系统操作日志"""
        log = SystemLog(
            user_id=user_id,
            action=action,
            target_type=target_type,
            target_id=target_id,
            details=details,
            ip_address=ip_address,
        )
        with self.get_session() as session:
            session.add(log)

    # ── 统计 ──────────────────────────────────────────────

    def get_statistics(self):
        """获取仪表盘统计数据"""
        with self.get_session() as session:
            total_users = session.query(func.count(User.id)).scalar()
            active_users = session.query(func.count(User.id)).filter(User.is_active).scalar()
            total_conversations = session.query(func.count(ConversationRecord.id)).scalar()
            pending_alerts = session.query(func.count(AlertLog.id)).filter(
                AlertLog.status == "pending"
            ).scalar()
            resolved_alerts = session.query(func.count(AlertLog.id)).filter(
                AlertLog.status == "resolved"
            ).scalar()
            total_alerts = session.query(func.count(AlertLog.id)).scalar()
            total_emotion_logs = session.query(func.count(EmotionLog.id)).scalar()

            # 各风险等级预警数
            risk_counts = dict(
                session.query(AlertLog.risk_level, func.count(AlertLog.id))
                       .group_by(AlertLog.risk_level).all()
            )

            return {
                "total_users": total_users,
                "active_users": active_users,
                "total_conversations": total_conversations,
                "total_emotion_logs": total_emotion_logs,
                "total_alerts": total_alerts,
                "pending_alerts": pending_alerts,
                "resolved_alerts": resolved_alerts,
                "risk_level_counts": risk_counts,
            }

    # ------------------------------------------------------------------
    # Convenience list wrappers (used by routes.py)
    # ------------------------------------------------------------------

    def list_conversations(self, **kwargs):
        return self.search_conversations(**kwargs)

    def list_emotion_logs(self, **kwargs):
        return self.get_emotion_logs(**kwargs)

    def list_alerts(self, **kwargs):
        return self.search_alerts(**kwargs)

    def list_system_logs(self, filters=None, page=1, per_page=50):
        filters = filters or {}
        session = ScopedSession()
        try:
            query = session.query(SystemLog)
            if filters.get('user_id'):
                query = query.filter(SystemLog.user_id == int(filters['user_id']))
            if filters.get('action'):
                query = query.filter(SystemLog.action.ilike('%' + filters['action'] + '%'))
            if filters.get('date_from'):
                query = query.filter(SystemLog.created_at >= filters['date_from'])
            if filters.get('date_to'):
                query = query.filter(SystemLog.created_at <= filters['date_to'])
            total = query.count()
            items_q = query.order_by(SystemLog.created_at.desc()).offset((page - 1) * per_page).limit(per_page).all()
            items = []
            for log in items_q:
                items.append({
                    'id': log.id, 'user_id': log.user_id,
                    'action': log.action, 'target_type': log.target_type,
                    'details': log.details, 'ip_address': log.ip_address,
                    'created_at': str(log.created_at) if log.created_at else None,
                })
            return {
                'items': items, 'total': total,
                'page': page, 'per_page': per_page,
                'total_pages': (total + per_page - 1) // per_page,
            }
        finally:
            ScopedSession.remove()

    def get_system_logs(self, filters=None, page=1, per_page=50):
        """获取系统操作日志（代理到 list_system_logs，兼容路由调用）"""
        return self.list_system_logs(filters=filters, page=page, per_page=per_page)

    # ------------------------------------------------------------------
    #  Student Management
    # ------------------------------------------------------------------

    def create_student(self, **kwargs):
        """添加学生"""
        with self.get_session() as session:
            student = Student(**kwargs)
            session.add(student)
            session.flush()
            return student.id

    def get_students(self, page=1, per_page=20, filters=None, counselor_id=None):
        """分页查询学生列表，可按辅导员过滤"""
        with self.get_session() as session:
            q = session.query(Student)
            if counselor_id:
                q = q.filter(Student.counselor_id == counselor_id)
            if filters:
                if filters.get("search"):
                    q = q.filter(Student.name.contains(filters["search"]))
                if filters.get("class_name"):
                    q = q.filter(Student.class_name == filters["class_name"])
                if filters.get("risk_level"):
                    q = q.filter(Student.risk_level == filters["risk_level"])
            total = q.count()
            items = q.order_by(Student.id.desc()).offset((page-1)*per_page).limit(per_page).all()
            return {"items": [self._to_dict(s) for s in items], "total": total, "page": page, "per_page": per_page}

    def update_student(self, student_id, updates):
        """更新学生信息"""
        with self.get_session() as session:
            s = session.query(Student).get(student_id)
            if s:
                for k, v in updates.items():
                    setattr(s, k, v)
                return True
            return False

    def create_student_profile(self, **kwargs):
        """添加学生档案"""
        with self.get_session() as session:
            p = StudentProfile(**kwargs)
            session.add(p)
            session.flush()
            return p.id

    def get_student_profiles(self, student_id, page=1, per_page=20):
        """分页查询学生档案"""
        with self.get_session() as session:
            q = session.query(StudentProfile).filter(StudentProfile.student_id == student_id)
            total = q.count()
            items = q.order_by(StudentProfile.id.desc()).offset((page-1)*per_page).limit(per_page).all()
            return {"items": [self._to_dict(p) for p in items], "total": total}

    def create_emotion_tracking(self, **kwargs):
        """创建情绪追踪记录"""
        auto_reminder = kwargs.pop("auto_reminder", True)
        with self.get_session() as session:
            t = EmotionTracker(**kwargs)
            session.add(t)
            session.flush()
            # Auto-generate reminder if high risk
            if auto_reminder and t.risk_level in ("high", "critical"):
                self._auto_generate_reminder(session, t)
            return t.id

    def _auto_generate_reminder(self, session, tracker):
        """高风险时自动生成提醒"""
        student = session.query(Student).get(tracker.student_id)
        if not student:
            return
        existing = session.query(Reminder).filter(
            Reminder.student_id == tracker.student_id,
            Reminder.is_completed == False,
            Reminder.reminder_type == "emotion_check"
        ).first()
        if not existing:
            r = Reminder(
                student_id=tracker.student_id,
                counselor_id=student.counselor_id,
                title=f"紧急关注: {student.name} 情绪异常",
                description=f"情绪类型: {tracker.emotion}, 强度: {tracker.intensity}/10",
                reminder_type="emotion_check",
                priority="high",
            )
            session.add(r)

    def get_emotion_tracking(self, student_id, days=30):
        """获取情绪追踪历史"""
        with self.get_session() as session:
            since = datetime.now() - timedelta(days=days)
            items = session.query(EmotionTracker).filter(
                EmotionTracker.student_id == student_id,
                EmotionTracker.created_at >= since
            ).order_by(EmotionTracker.created_at.desc()).all()
            return [self._to_dict(t) for t in items]

    def get_reminders(self, counselor_id=None, page=1, per_page=20):
        """获取提醒列表"""
        with self.get_session() as session:
            q = session.query(Reminder)
            if counselor_id:
                q = q.filter(Reminder.counselor_id == counselor_id)
            q = q.filter(Reminder.is_completed == False)
            total = q.count()
            items = q.order_by(Reminder.priority.desc(), Reminder.created_at.desc()).offset((page-1)*per_page).limit(per_page).all()
            return {"items": [self._to_dict(r) for r in items], "total": total}

    def complete_reminder(self, reminder_id):
        """标记提醒为已完成"""
        with self.get_session() as session:
            r = session.query(Reminder).get(reminder_id)
            if r:
                r.is_completed = True
                return True
            return False

    def get_student_stats(self):
        """获取学生统计数据"""
        with self.get_session() as session:
            total = session.query(func.count(Student.id)).scalar()
            high_risk = session.query(func.count(Student.id)).filter(Student.risk_level == "high").scalar()
            medium_risk = session.query(func.count(Student.id)).filter(Student.risk_level == "medium").scalar()
            pending_reminders = session.query(func.count(Reminder.id)).filter(Reminder.is_completed == False).scalar()
            return {
                "total_students": total or 0,
                "high_risk": high_risk or 0,
                "medium_risk": medium_risk or 0,
                "pending_reminders": pending_reminders or 0,
            }

    # ------------------------------------------------------------------
    #  情绪网络图 (Emotion Network Graph)
    # ------------------------------------------------------------------

    def get_emotion_network(self, counselor_id=None, role=None):
        """构建情绪网络图数据：中心 → 情绪分支 → 学生节点（按严重程度着色）。

        辅导员仅返回本人学生；管理员/学工返回全部学生。
        返回结构：
        {
            "root":   {"name": ..., "college": ..., "total": ...},
            "groups": [{"emotion","icon","color","severity","count","high","medium","low",
                        "students": [{"db_id","student_no","name","class_name","college",
                                      "risk_level","emotion_status"}]}],
            "stats":  {"total","high","medium","low"},
            "updated_at": "...",
        }
        """
        with self.get_session() as session:
            q = session.query(Student).filter(Student.is_active == True)
            root_name = "全校学生"
            college = ""
            if role == "counselor" and counselor_id:
                q = q.filter(Student.counselor_id == counselor_id)
                user = session.query(User).get(counselor_id)
                if user:
                    root_name = user.display_name
                    college = user.college
            students = q.all()

            groups_map = {}
            for s in students:
                emotion = s.emotion_status or "正常"
                risk = s.risk_level or "low"
                if risk not in ("high", "medium", "low"):
                    risk = "low"
                meta = EMOTION_NETWORK_META.get(
                    emotion, {"icon": "🤔", "color": "#94a3b8", "severity": 1}
                )
                grp = groups_map.setdefault(emotion, {
                    "emotion": emotion,
                    "icon": meta["icon"],
                    "color": meta["color"],
                    "severity": meta["severity"],
                    "count": 0, "high": 0, "medium": 0, "low": 0,
                    "students": [],
                })
                grp["count"] += 1
                grp[risk] += 1
                grp["students"].append({
                    "db_id": s.id,
                    "student_no": s.student_id,
                    "name": s.name,
                    "class_name": s.class_name or "",
                    "college": s.college or "",
                    "risk_level": risk,
                    "emotion_status": emotion,
                })

            # 负向情绪排前，组内高风险学生排前
            groups = sorted(groups_map.values(), key=lambda g: (-g["severity"], -g["count"]))
            risk_order = {"high": 0, "medium": 1, "low": 2}
            for g in groups:
                g["students"].sort(key=lambda s: risk_order.get(s["risk_level"], 2))

            total = len(students)
            high = sum(1 for s in students if (s.risk_level or "low") == "high")
            medium = sum(1 for s in students if (s.risk_level or "low") == "medium")
            low = total - high - medium
            return {
                "root": {"name": root_name, "college": college, "total": total},
                "groups": groups,
                "stats": {"total": total, "high": high, "medium": medium, "low": low},
                "updated_at": str(datetime.now()),
            }

    def get_test_accounts(self):
        """动态生成测试账号列表（教师端 + 学生端），供登录页渲染，避免硬编码错位。"""
        with self.get_session() as session:
            # 学工处 / 管理员
            staff_users = session.query(User).filter(
                User.role.in_(["super_admin", "student_affairs"]),
                User.is_active == True,
            ).order_by(User.id).all()
            staff_items = [{
                "username": u.username,
                "display_name": u.display_name,
                "role": u.role,
            } for u in staff_users]

            # 辅导员 + 每名辅导员前 3 名示例学生
            counselors = session.query(User).filter(
                User.role == "counselor", User.is_active == True
            ).order_by(User.id).all()
            counselor_items = []
            for u in counselors:
                student_count = session.query(func.count(Student.id)).filter(
                    Student.counselor_id == u.id, Student.is_active == True
                ).scalar() or 0
                samples = session.query(Student).filter(
                    Student.counselor_id == u.id, Student.is_active == True
                ).order_by(Student.student_id).limit(3).all()
                counselor_items.append({
                    "username": u.username,
                    "display_name": u.display_name,
                    "college": u.college,
                    "student_count": student_count,
                    "students": [{
                        "student_id": s.student_id,
                        "name": s.name,
                        "class_name": s.class_name,
                    } for s in samples],
                })
            return {"staff": staff_items, "counselors": counselor_items}

    # ------------------------------------------------------------------
    #  Student Auth (学生登录)
    # ------------------------------------------------------------------

    def get_student_by_student_id(self, student_id):
        """根据学号获取学生"""
        with self.get_session() as session:
            student = session.query(Student).filter(Student.student_id == student_id).first()
            if student is None:
                return None
            return self._to_dict(student)

    def authenticate_student(self, student_id, password):
        """学生认证"""
        student = self.get_student_by_student_id(student_id)
        if student is None or not student.get("is_active", True):
            return None
        if not student.get("password_hash"):
            return None
        if not check_password_hash(student["password_hash"], password):
            return None
        # 更新最后登录时间
        self.update_student_login_time(student["id"])
        return student

    def update_student_login_time(self, student_id):
        """更新学生最后登录时间"""
        with self.get_session() as session:
            session.query(Student).filter(Student.id == student_id).update(
                {"last_login": datetime.now()}
            )

    def set_student_password(self, student_id, password):
        """设置学生密码"""
        password_hash = generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)
        with self.get_session() as session:
            session.query(Student).filter(Student.id == student_id).update(
                {"password_hash": password_hash}
            )
            return True

    def get_student_by_id(self, student_id):
        """根据ID获取学生"""
        with self.get_session() as session:
            student = session.query(Student).filter(Student.id == student_id).first()
            if student is None:
                return None
            return self._to_dict(student)

    def find_student_for_realtime_summary(self, student_pk=None, student_id_str=None, student_name=None):
        """Find video-call student by primary key, student number or name."""
        with self.get_session() as session:
            student = None
            if student_pk:
                student = session.query(Student).filter(Student.id == student_pk).first()
            if not student and student_id_str:
                student = session.query(Student).filter(Student.student_id == str(student_id_str)).first()
            if not student and student_name:
                student = session.query(Student).filter(Student.name == student_name).first()
            return self._to_dict(student) if student else None

    def update_student_risk_state(self, student_id, risk_level, emotion_status):
        """Update current student risk state and emotion status."""
        with self.get_session() as session:
            student = session.query(Student).get(student_id)
            if not student:
                return False
            student.risk_level = risk_level or student.risk_level
            student.emotion_status = emotion_status or student.emotion_status
            student.updated_at = datetime.now()
            return True

    def create_realtime_followup_reminder(self, student_id, counselor_id, title, description, priority, due_date):
        """Create or update a video-call emotion follow-up reminder."""
        with self.get_session() as session:
            day_start = due_date.replace(hour=0, minute=0, second=0, microsecond=0) if due_date else None
            day_end = day_start + timedelta(days=1) if day_start else None
            existing = None
            if day_start and day_end:
                existing = session.query(Reminder).filter(
                    Reminder.student_id == student_id,
                    Reminder.counselor_id == counselor_id,
                    Reminder.reminder_type == "realtime_emotion_followup",
                    Reminder.is_completed == False,
                    Reminder.due_date >= day_start,
                    Reminder.due_date < day_end,
                ).first()
            if existing:
                existing.title = title
                existing.description = description
                existing.priority = priority
                existing.due_date = due_date
                session.flush()
                return existing.id
            reminder = Reminder(
                student_id=student_id,
                counselor_id=counselor_id,
                title=title,
                description=description,
                reminder_type="realtime_emotion_followup",
                priority=priority,
                due_date=due_date,
            )
            session.add(reminder)
            session.flush()
            return reminder.id

    # ------------------------------------------------------------------
    #  Messages (即时通讯)
    # ------------------------------------------------------------------

    def create_message(self, student_id, counselor_id, sender_type, sender_id, content, message_type="text", file_url=None):
        """创建消息"""
        with self.get_session() as session:
            msg = Message(
                student_id=student_id,
                counselor_id=counselor_id,
                sender_type=sender_type,
                sender_id=sender_id,
                content=content,
                message_type=message_type,
                file_url=file_url,
            )
            session.add(msg)
            session.flush()
            return msg.id

    def get_conversation_messages(self, student_id, counselor_id, page=1, per_page=50):
        """获取学生与辅导员的对话消息"""
        with self.get_session() as session:
            query = session.query(Message).filter(
                Message.student_id == student_id,
                Message.counselor_id == counselor_id,
            )
            total = query.count()
            items = query.order_by(Message.created_at.desc(), Message.id.desc()).offset((page-1)*per_page).limit(per_page).all()
            return {"items": [self._to_dict(m) for m in items], "total": total}

    def mark_messages_read(self, student_id, counselor_id, reader_type):
        """标记消息为已读"""
        with self.get_session() as session:
            if reader_type == "student":
                session.query(Message).filter(
                    Message.student_id == student_id,
                    Message.counselor_id == counselor_id,
                    Message.sender_type == "counselor",
                    Message.is_read == False,
                ).update({"is_read": True})
            else:
                session.query(Message).filter(
                    Message.student_id == student_id,
                    Message.counselor_id == counselor_id,
                    Message.sender_type == "student",
                    Message.is_read == False,
                ).update({"is_read": True})

    def get_unread_count(self, user_id, user_type):
        """获取未读消息数量"""
        with self.get_session() as session:
            if user_type == "student":
                count = session.query(func.count(Message.id)).filter(
                    Message.student_id == user_id,
                    Message.sender_type == "counselor",
                    Message.is_read == False,
                ).scalar()
            else:
                count = session.query(func.count(Message.id)).filter(
                    Message.counselor_id == user_id,
                    Message.sender_type == "student",
                    Message.is_read == False,
                ).scalar()
            return count or 0

    def get_message_contacts(self, user_id, user_type):
        """获取消息联系人列表（JOIN 查询；消息预览按 created_at 最新为准）"""
        with self.get_session() as session:
            if user_type == "student":
                contacts = []
                latest_time_sub = session.query(
                    Message.counselor_id,
                    func.max(Message.created_at).label('latest_time')
                ).filter(Message.student_id == user_id).group_by(Message.counselor_id).subquery()
                last_msg_sub = session.query(
                    Message.counselor_id,
                    func.max(Message.id).label('max_id')
                ).join(
                    latest_time_sub,
                    (Message.counselor_id == latest_time_sub.c.counselor_id) &
                    (Message.created_at == latest_time_sub.c.latest_time)
                ).filter(Message.student_id == user_id).group_by(Message.counselor_id).subquery()
                unread_sub = session.query(
                    Message.counselor_id,
                    func.count(Message.id).label('unread')
                ).filter(
                    Message.student_id == user_id,
                    Message.sender_type == "counselor",
                    Message.is_read == False
                ).group_by(Message.counselor_id).subquery()
                results = session.query(
                    User, Message, func.coalesce(unread_sub.c.unread, 0)
                ).join(last_msg_sub, User.id == last_msg_sub.c.counselor_id
                ).join(Message, Message.id == last_msg_sub.c.max_id
                ).outerjoin(unread_sub, User.id == unread_sub.c.counselor_id
                ).order_by(Message.created_at.desc(), Message.id.desc()).all()
                seen_ids = set()
                for user, msg, unread in results:
                    seen_ids.add(user.id)
                    contacts.append({
                        "id": user.id, "name": user.display_name, "role": "counselor",
                        "last_message": self._to_dict(msg) if msg else None,
                        "unread_count": unread or 0,
                    })
                student = session.query(Student).filter(Student.id == user_id).first()
                if student and student.counselor_id and student.counselor_id not in seen_ids:
                    counselor = session.query(User).get(student.counselor_id)
                    if counselor:
                        contacts.insert(0, {
                            "id": counselor.id, "name": counselor.display_name, "role": "counselor",
                            "last_message": None, "unread_count": 0,
                        })
                return contacts
            else:
                contacts = []
                latest_time_sub = session.query(
                    Message.student_id,
                    func.max(Message.created_at).label('latest_time')
                ).filter(Message.counselor_id == user_id).group_by(Message.student_id).subquery()
                last_msg_sub = session.query(
                    Message.student_id,
                    func.max(Message.id).label('max_id')
                ).join(
                    latest_time_sub,
                    (Message.student_id == latest_time_sub.c.student_id) &
                    (Message.created_at == latest_time_sub.c.latest_time)
                ).filter(Message.counselor_id == user_id).group_by(Message.student_id).subquery()
                unread_sub = session.query(
                    Message.student_id,
                    func.count(Message.id).label('unread')
                ).filter(
                    Message.counselor_id == user_id,
                    Message.sender_type == "student",
                    Message.is_read == False
                ).group_by(Message.student_id).subquery()
                results = session.query(
                    Student, Message, func.coalesce(unread_sub.c.unread, 0)
                ).join(last_msg_sub, Student.id == last_msg_sub.c.student_id
                ).join(Message, Message.id == last_msg_sub.c.max_id
                ).outerjoin(unread_sub, Student.id == unread_sub.c.student_id
                ).order_by(Message.created_at.desc(), Message.id.desc()).all()
                for stu, msg, unread in results:
                    contacts.append({
                        "id": stu.id, "name": stu.name,
                        "student_id": stu.student_id,
                        "role": "student",
                        "last_message": self._to_dict(msg) if msg else None,
                        "unread_count": unread or 0,
                    })
                return contacts

    # ------------------------------------------------------------------
    #  Appointments (预约)
    # ------------------------------------------------------------------

    def create_appointment(self, student_id, counselor_id, appointment_time, reason="", duration=30):
        """创建预约"""
        with self.get_session() as session:
            appt = Appointment(
                student_id=student_id,
                counselor_id=counselor_id,
                appointment_time=appointment_time,
                reason=reason,
                duration=duration,
            )
            session.add(appt)
            session.flush()
            return appt.id

    def get_appointments(self, user_id, user_type, status=None, page=1, per_page=20):
        """获取预约列表"""
        with self.get_session() as session:
            query = session.query(Appointment)
            if user_type == "student":
                query = query.filter(Appointment.student_id == user_id)
            else:
                query = query.filter(Appointment.counselor_id == user_id)
            if status:
                query = query.filter(Appointment.status == status)
            total = query.count()
            items = query.order_by(Appointment.appointment_time.desc()).offset((page-1)*per_page).limit(per_page).all()
            return {"items": [self._to_dict(a) for a in items], "total": total}

    def update_appointment_status(self, appointment_id, status, notes=None):
        """更新预约状态"""
        with self.get_session() as session:
            updates = {"status": status}
            if notes:
                updates["notes"] = notes
            session.query(Appointment).filter(Appointment.id == appointment_id).update(updates)
            return True

    def get_calendar_events(self, year, month):
        """获取日历月的提醒和跟进事件"""
        with self.get_session() as session:
            start = datetime(year, month, 1)
            if month == 12:
                end = datetime(year+1, 1, 1)
            else:
                end = datetime(year, month+1, 1)
            reminders = session.query(Reminder).filter(
                Reminder.due_date >= start,
                Reminder.due_date < end
            ).all()
            profiles = session.query(StudentProfile).filter(
                StudentProfile.follow_up_date >= start,
                StudentProfile.follow_up_date < end,
                StudentProfile.follow_up_needed == True
            ).all()
            events = []
            for r in reminders:
                events.append({
                    "date": r.due_date.strftime("%Y-%m-%d") if r.due_date else "",
                    "title": r.title,
                    "type": "reminder",
                    "priority": r.priority,
                })
            for p in profiles:
                events.append({
                    "date": p.follow_up_date.strftime("%Y-%m-%d") if p.follow_up_date else "",
                    "title": "跟进: " + (p.student.name if p.student else ""),
                    "type": "follow_up",
                    "priority": "medium",
                })
            return events

    # ------------------------------------------------------------------
    #  Export
    # ------------------------------------------------------------------
    def export_data(self, export_type, filters=None):
        filters = filters or {}
        if export_type == 'conversations':
            return self.search_conversations(page=1, per_page=10000).get('items', [])
        elif export_type == 'emotions':
            return self.get_emotion_logs(page=1, per_page=10000).get('items', [])
        elif export_type == 'alerts':
            return self.search_alerts(page=1, per_page=10000).get('items', [])
        return []

    # ------------------------------------------------------------------
    #  Counselors (辅导员列表)
    # ------------------------------------------------------------------
    def get_counselors(self):
        """获取所有在职辅导员列表"""
        with self.get_session() as session:
            users = session.query(User).filter(
                User.role == "counselor",
                User.is_active == True
            ).all()
            return [{
                "id": u.id,
                "display_name": u.display_name,
                "college": u.college,
                "phone": u.phone,
            } for u in users]

    # ------------------------------------------------------------------
    #  Todo CRUD (自定义待办)
    # ------------------------------------------------------------------
    def create_todo(self, user_id, title, description="", category="work_task",
                    priority="medium", due_date=None):
        """创建自定义待办"""
        with self.get_session() as session:
            todo = Todo(
                user_id=user_id, title=title, description=description,
                category=category, priority=priority, due_date=due_date,
            )
            session.add(todo)
            session.flush()
            return todo.id

    def get_todos(self, user_id=None, category=None, is_completed=False,
                  page=1, per_page=50):
        """查询待办列表"""
        with self.get_session() as session:
            q = session.query(Todo)
            if user_id:
                q = q.filter(Todo.user_id == user_id)
            if category:
                q = q.filter(Todo.category == category)
            q = q.filter(Todo.is_completed == is_completed)
            total = q.count()
            items = q.order_by(Todo.priority.desc(), Todo.due_date.asc())\
                     .offset((page - 1) * per_page).limit(per_page).all()
            return {"items": [self._to_dict(t) for t in items], "total": total}

    def complete_todo(self, todo_id):
        """标记待办为已完成"""
        with self.get_session() as session:
            t = session.query(Todo).get(todo_id)
            if t:
                t.is_completed = True
                return True
            return False

    def delete_todo(self, todo_id):
        """删除待办"""
        with self.get_session() as session:
            t = session.query(Todo).get(todo_id)
            if t:
                session.delete(t)
                return True
            return False

    # ------------------------------------------------------------------
    #  Assessment (心理测评)
    # ------------------------------------------------------------------
    def save_assessment(self, student_id, phq9_score, phq9_level, gad7_score,
                        gad7_level, isi_score, isi_level, item9_score,
                        answers, duration_seconds):
        """保存测评结果"""
        with self.get_session() as session:
            r = AssessmentResult(
                student_id=student_id, phq9_score=phq9_score,
                phq9_level=phq9_level, gad7_score=gad7_score,
                gad7_level=gad7_level, isi_score=isi_score,
                isi_level=isi_level, item9_score=item9_score,
                answers=answers, duration_seconds=duration_seconds,
            )
            session.add(r)
            session.flush()
            return r.id

    def get_assessments(self, student_id=None, page=1, per_page=10):
        """查询测评历史"""
        with self.get_session() as session:
            q = session.query(AssessmentResult)
            if student_id:
                q = q.filter(AssessmentResult.student_id == student_id)
            total = q.count()
            items = q.order_by(AssessmentResult.created_at.desc())\
                     .offset((page-1)*per_page).limit(per_page).all()
            return {"items": [self._to_dict(i) for i in items], "total": total}

    # ── 工作台数据（DatabaseManager 方法）──────────────────

    def get_day_detail(self, date_str, counselor_id=None):
        """获取指定日期的详细待办列表"""
        from datetime import datetime as _dt
        with self.get_session() as session:
            target = _dt.strptime(date_str, "%Y-%m-%d")
            next_day = target + timedelta(days=1)

            q = session.query(Reminder).filter(
                Reminder.due_date >= target,
                Reminder.due_date < next_day,
            )

            reminders = q.order_by(Reminder.due_date).all()
            result = []
            for r in reminders:
                stu_name = r.student.name if r.student else ""
                result.append({
                    "id": r.id,
                    "type": r.reminder_type,
                    "title": r.title,
                    "student_name": stu_name,
                    "student_id": r.student.student_id if r.student else "",
                    "priority": r.priority,
                    "due_date": r.due_date.strftime("%H:%M") if r.due_date else "",
                    "description": r.description or "",
                    "is_completed": r.is_completed,
                })
            return result
    def get_today_workplan(self, counselor_id=None):
        """获取今日工作台数据：今日+未来3天待办、风险学生、日历事件、自定义Todo"""
        with self.get_session() as session:
            today = datetime.now()
            today_str = today.strftime("%Y-%m-%d")
            future = today + timedelta(days=3)

            # 1. 提醒：只取今天到未来3天的（不包含全部历史）
            q_reminder = session.query(Reminder).filter(
                Reminder.is_completed == False,
                Reminder.due_date >= today,
                Reminder.due_date <= future,
            )
            if counselor_id:
                q_reminder = q_reminder.filter(Reminder.counselor_id == counselor_id)
            today_reminders = q_reminder.order_by(Reminder.priority.desc(), Reminder.due_date.asc()).limit(10).all()
            reminder_items = []
            for r in today_reminders:
                stu_name = r.student.name if r.student else "未知"
                reminder_items.append({
                    "id": f"rem_{r.id}", "source": "reminder",
                    "category": "student_care",
                    "title": r.title, "student_name": stu_name,
                    "student_id": r.student.student_id if r.student else "",
                    "priority": r.priority,
                    "due_date": r.due_date.strftime("%Y-%m-%d %H:%M") if r.due_date else today_str,
                    "description": r.description or "",
                })

            # 2. 高风险学生（最多5个，仅显示此辅导员的学生）
            if counselor_id:
                high_risk_students = session.query(Student).filter(
                    Student.risk_level == "high", Student.is_active == True,
                    Student.counselor_id == counselor_id,
                ).limit(5).all()
            else:
                high_risk_students = session.query(Student).filter(
                    Student.risk_level == "high", Student.is_active == True,
                ).limit(5).all()
            for s in high_risk_students:
                reminder_items.append({
                    "id": f"risk_high_{s.id}", "source": "risk",
                    "category": "student_care",
                    "title": f"【高风险】跟进关注 {s.name}",
                    "student_name": s.name, "student_id": s.student_id,
                    "priority": "high", "due_date": today_str,
                    "description": f"情绪状态：{s.emotion_status}",
                })

            # 3. 中风险学生（周一显示，最多3个，仅此辅导员的学生）
            if today.weekday() == 0:
                if counselor_id:
                    medium_risk = session.query(Student).filter(
                        Student.risk_level == "medium", Student.is_active == True,
                        Student.counselor_id == counselor_id,
                    ).limit(3).all()
                else:
                    medium_risk = session.query(Student).filter(
                        Student.risk_level == "medium", Student.is_active == True,
                    ).limit(3).all()
                for s in medium_risk:
                    reminder_items.append({
                        "id": f"risk_med_{s.id}", "source": "risk",
                        "category": "student_care",
                        "title": f"【中风险】本周跟进 {s.name}",
                        "student_name": s.name, "student_id": s.student_id,
                        "priority": "medium", "due_date": today_str,
                        "description": f"情绪状态：{s.emotion_status}",
                    })

            # 4. 自定义Todo（未完成的）
            if counselor_id:
                todos = session.query(Todo).filter(
                    Todo.user_id == counselor_id,
                    Todo.is_completed == False,
                ).order_by(Todo.priority.desc(), Todo.due_date.asc()).limit(15).all()
                for t in todos:
                    reminder_items.append({
                        "id": f"todo_{t.id}", "source": "todo",
                        "category": t.category or "work_task",
                        "title": t.title, "student_name": "",
                        "student_id": "", "priority": t.priority,
                        "due_date": t.due_date.strftime("%Y-%m-%d %H:%M") if t.due_date else today_str,
                        "description": t.description or "",
                    })

            # 5. 日历事件 — 当月全月视图，但事件限制±7天避免过载
            month_start = today.replace(day=1)
            if today.month == 12:
                month_end = today.replace(year=today.year+1, month=1, day=1)
            else:
                month_end = today.replace(month=today.month+1, day=1)
            cal_query_start = today - timedelta(days=7)
            cal_query_end = today + timedelta(days=7)

            if counselor_id:
                all_reminders = session.query(Reminder).filter(
                    Reminder.due_date >= cal_query_start, Reminder.due_date <= cal_query_end,
                    Reminder.counselor_id == counselor_id,
                ).all()
            else:
                all_reminders = session.query(Reminder).filter(
                    Reminder.due_date >= cal_query_start, Reminder.due_date <= cal_query_end,
                ).all()
            calendar_events = []
            for r in all_reminders:
                stu_name = r.student.name if r.student else ""
                calendar_events.append({
                    "date": r.due_date.strftime("%Y-%m-%d") if r.due_date else "",
                    "title": r.title, "type": "reminder",
                    "priority": r.priority, "student_name": stu_name,
                })
            # 高风险学生每日跟进到日历
            for s in high_risk_students:
                calendar_events.append({
                    "date": today_str, "title": f"每日跟进：{s.name}",
                    "type": "high_risk", "priority": "high", "student_name": s.name,
                })
            # 自定义Todo到日历
            if counselor_id:
                todo_events = session.query(Todo).filter(
                    Todo.user_id == counselor_id, Todo.is_completed == False,
                    Todo.due_date >= month_start, Todo.due_date < month_end,
                ).all()
                for t in todo_events:
                    calendar_events.append({
                        "date": t.due_date.strftime("%Y-%m-%d") if t.due_date else "",
                        "title": t.title, "type": "todo",
                        "priority": t.priority, "student_name": "",
                    })

            # 6. 统计摘要（仅统计此辅导员的学生）
            if counselor_id:
                total_students = session.query(func.count(Student.id)).filter(
                    Student.counselor_id == counselor_id, Student.is_active == True).scalar() or 0
                high_count = session.query(func.count(Student.id)).filter(
                    Student.counselor_id == counselor_id,
                    Student.risk_level == "high", Student.is_active == True).scalar() or 0
                medium_count = session.query(func.count(Student.id)).filter(
                    Student.counselor_id == counselor_id,
                    Student.risk_level == "medium", Student.is_active == True).scalar() or 0
            else:
                total_students = session.query(func.count(Student.id)).scalar() or 0
                high_count = session.query(func.count(Student.id)).filter(
                    Student.risk_level == "high", Student.is_active == True).scalar() or 0
                medium_count = session.query(func.count(Student.id)).filter(
                    Student.risk_level == "medium", Student.is_active == True).scalar() or 0
            low_count = total_students - high_count - medium_count

            return {
                "date": today_str,
                "weekday": ["周一","周二","周三","周四","周五","周六","周日"][today.weekday()],
                "todo_list": reminder_items,
                "todo_count": len(reminder_items),
                "calendar_events": calendar_events,
                "student_summary": {
                    "total": total_students,
                    "high_risk": high_count,
                    "medium_risk": medium_count,
                    "low_risk": low_count,
                },
                "pending_reminders": len(reminder_items),
            }


class AuthManager:
    """用户认证管理器 - 密码处理、JWT风格Token生成与验证"""

    # 默认密钥，生产环境应从配置中读取；为空时使用开发回退值（app.py 会在生产环境强制校验）
    SECRET_KEY = Config.SECRET_KEY or "lingxin-dev-secret-key-change-in-production"
    TOKEN_MAX_AGE = 86400  # 24小时

    def __init__(self, db_manager: DatabaseManager):
        self.db = db_manager
        self.serializer = Serializer(self.SECRET_KEY)

    # ── 密码处理 ──────────────────────────────────────────

    @staticmethod
    def hash_password(password: str) -> str:
        """生成密码哈希"""
        return generate_password_hash(password, method="pbkdf2:sha256", salt_length=16)

    @staticmethod
    def verify_password(password: str, password_hash: str) -> bool:
        """验证密码"""
        return check_password_hash(password_hash, password)

    # ── 用户管理 ──────────────────────────────────────────

    def create_user(self, username, password, role, display_name, college,
                    phone=""):
        """创建新用户（带密码哈希）"""
        # 检查用户名是否已存在
        if self.db.get_user_by_username(username):
            raise ValueError(f"用户名 '{username}' 已存在")

        pw_hash = self.hash_password(password)
        return self.db.create_user(
            username=username,
            password_hash=pw_hash,
            display_name=display_name,
            role=role,
            college=college,
            phone=phone,
        )

    def authenticate(self, username: str, password: str):
        """用户认证 - 成功返回用户对象，失败返回None"""
        user = self.db.get_user_by_username(username)
        if user is None or not user.get("is_active", True):
            return None
        if not self.verify_password(password, user.get("password_hash", "")):
            return None

        # 更新最后登录时间
        self.db.update_user(user["id"], last_login=datetime.now())
        return user

    def get_user(self, user_id):
        """根据用户 ID 获取用户信息（字典，会话内完成序列化）"""
        with self.db.get_session() as session:
            user = session.query(User).filter(User.id == user_id).first()
            if user is None:
                return None
            return self.db._to_dict(user)

    def update_user(self, user_id, updates):
        """更新用户资料（字段名对齐，name → display_name）"""
        field_map = {"name": "display_name"}
        mapped = {}
        for k, v in (updates or {}).items():
            k2 = field_map.get(k, k)
            if k2 in ("display_name", "role", "college", "phone", "is_active"):
                mapped[k2] = v
        if not mapped:
            return False
        return self.db.update_user(user_id, **mapped)

    # ── Token管理 ─────────────────────────────────────────

    def generate_token(self, user) -> str:
        """生成Token（基于itsdangerous的签名Token），包含jti用于撤销"""
        import uuid
        uid = user["id"] if isinstance(user, dict) else user.id
        uname = user["username"] if isinstance(user, dict) else user.username
        role = user["role"] if isinstance(user, dict) else user.role
        return self.serializer.dumps({
            "user_id": uid,
            "username": uname,
            "role": role,
            "jti": str(uuid.uuid4()),  # 唯一标识用于撤销
        })

    def verify_token(self, token: str, max_age=None):
        """验证Token - 成功返回用户数据dict，失败返回None。同时检查黑名单。"""
        max_age = max_age or self.TOKEN_MAX_AGE
        try:
            data = self.serializer.loads(token, max_age=max_age)
        except (SignatureExpired, BadSignature):
            return None
        # 检查Token是否在黑名单中
        jti = data.get("jti", "")
        if jti and self._is_token_revoked(jti):
            return None
        return data

    def revoke_token(self, token: str):
        """将Token加入黑名单，使其不可再使用"""
        try:
            # 尝试解析Token获取jti（即使过期也可获取）
            data = self.serializer.loads(token, max_age=None)
        except Exception:
            # Token格式无效或过期太久，无需撤销
            return True
        jti = data.get("jti", "")
        if not jti:
            return False
        with self.db.get_session() as session:
            existing = session.query(TokenBlacklist).filter(
                TokenBlacklist.token_jti == jti).first()
            if existing:
                return True
            session.add(TokenBlacklist(
                token_jti=jti,
                expires_at=datetime.now() + timedelta(hours=24),
            ))
            session.commit()
        return True

    def _is_token_revoked(self, jti: str) -> bool:
        """检查Token是否已被撤销"""
        if not jti:
            return False
        with self.db.get_session() as session:
            return session.query(TokenBlacklist).filter(
                TokenBlacklist.token_jti == jti).first() is not None

    # ── 学生认证 ─────────────────────────────────────────

    def authenticate_student(self, student_id: str, password: str):
        """学生认证 - 成功返回学生对象，失败返回None"""
        student = self.db.get_student_by_student_id(student_id)
        if student is None or not student.get("is_active", True):
            return None
        if not student.get("password_hash"):
            return None
        if not check_password_hash(student["password_hash"], password):
            return None
        # 更新最后登录时间
        self.db.update_student_login_time(student["id"])
        return student

    def generate_student_token(self, student) -> str:
        """生成学生Token"""
        sid = student["id"] if isinstance(student, dict) else student.id
        student_id = student["student_id"] if isinstance(student, dict) else student.student_id
        name = student["name"] if isinstance(student, dict) else student.name
        return self.serializer.dumps({
            "student_id": sid,
            "student_id_str": student_id,
            "name": name,
            "role": "student",
            "user_type": "student",
        })

# ===================================================================
#  全局单例
# ===================================================================

db_manager = DatabaseManager()
auth_manager = AuthManager(db_manager)


# ===================================================================
#  主入口 - 建表并填充示例数据
# ===================================================================

if __name__ == "__main__":
    print("=" * 60)
    print("聆心 - 数据库初始化")
    print("=" * 60)

    dm = DatabaseManager()
    am = AuthManager(dm)

    # 创建所有表
    dm.init_db()

    # 填充示例数据
    print("\n📋 正在填充示例数据...")

    try:
        # 创建管理员
        admin_id = am.create_user(
            username="admin",
            password="admin123",
            role="super_admin",
            display_name="系统管理员",
            college="信息中心",
            phone="13800000001",
        )
        print(f"  [OK] 管理员: admin (id={admin_id})")

        # 创建辅导员
        counselor_id = am.create_user(
            username="zhangwei",
            password="counsel123",
            role="counselor",
            display_name="张伟",
            college="计算机学院",
            phone="13800000002",
        )
        print(f"  [OK] 辅导员: zhangwei (id={counselor_id})")

        # 创建学工人员
        staff_id = am.create_user(
            username="liuxin",
            password="staff123",
            role="student_affairs",
            display_name="刘鑫",
            college="学生工作处",
            phone="13800000003",
        )
        print(f"  [OK] 学工人员: liuxin (id={staff_id})")

        # 创建咨询记录
        conv_id = dm.create_conversation(
            counselor_id=counselor_id,
            student_name="王小明",
            student_class="计算机2022级1班",
            topic="学业压力咨询",
            content="学生反映近期课程压力大，特别是算法课程，感觉跟不上进度，晚上经常失眠。",
            structured_content="学业压力：算法课程学习困难，进度落后；睡眠问题：近期失眠。",
            emotion_tags={"primary": "anxious", "secondary": "stressed", "score": 0.82},
            risk_level="medium",
            status="completed",
        )
        print(f"  [OK] 咨询记录 id={conv_id}")

        # 创建情绪日志
        elog_id = dm.create_emotion_log(
            student_name="王小明",
            student_class="计算机2022级1班",
            emotion="anxious",
            emotion_id=3,
            confidence=0.82,
            intensity=7,
            audio_path="/audio/2024/wangxiaoming_001.wav",
            risk_level="medium",
            analyzed_by=counselor_id,
        )
        print(f"  [OK] 情绪日志 id={elog_id}")

        # 创建预警
        alert_id = dm.create_alert(
            student_name="李思远",
            student_class="外语2021级2班",
            risk_level="high",
            emotion_type="sad",
            intensity=9,
            description="语音分析显示持续低落情绪，强度高，需重点关注。",
            assigned_to=counselor_id,
        )
        print(f"  [OK] 预警 id={alert_id}")

        # 操作日志
        dm.log_action(
            user_id=admin_id,
            action="系统初始化",
            target_type="system",
            details={"message": "数据库初始化完成"},
        )

        # 显示统计
        stats = dm.get_statistics()
        print(f"\n# 数据库统计:")
        print(f"  用户总数: {stats['total_users']}")
        print(f"  咨询记录: {stats['total_conversations']}")
        print(f"  情绪日志: {stats['total_emotion_logs']}")
        print(f"  预警总数: {stats['total_alerts']}（待处理: {stats['pending_alerts']}）")

        # 测试认证
        print("\n🔐 认证测试:")
        user = am.authenticate("admin", "admin123")
        print(f"  admin 登录: {'[OK] 成功' if user else '[X] 失败'}")
        token = am.generate_token(user)
        print(f"  Token 生成: {token[:30]}...")
        verified = am.verify_token(token)
        print(f"  Token 验证: {'[OK] 通过' if verified else '[X] 失败'}")

        print("\n" + "=" * 60)
        print("[OK] 数据库初始化完成！")
        print("=" * 60)

    except Exception as e:
        print(f"\n[X] 错误: {e}")
        import traceback
        traceback.print_exc()







