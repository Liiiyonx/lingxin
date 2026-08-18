"""

提供认证、会话管理、情绪分析、预警、知识库及系统管理等完整接口。
"""

import os
import tempfile
import csv
import io
import json
import uuid
import logging
from datetime import datetime, timedelta
from functools import wraps

from flask import (
    Blueprint,
    request,
    jsonify,
    g,
    Response,
    current_app,
    send_file,
)

from core.rag_engine import KnowledgeBaseManager, RAGGenerator
from core.emotion_engine import EmotionAnalyzer, RiskAlertSystem
from core.prompt_engine import ConversationEngine, PromptManager
from core.database import DatabaseManager, AuthManager
from core.realtime_emotion import get_or_create_analyzer, cleanup_session
from config.config import load_config

# ---------------------------------------------------------------------------
# Blueprint & configuration
# ---------------------------------------------------------------------------

api = Blueprint("api", __name__, url_prefix="/api")

logger = logging.getLogger("api.routes")

config = load_config()

# —— 简单内存级登录速率限制（防暴力破解） ——
from collections import defaultdict
_login_attempts = defaultdict(list)
_LOGIN_MAX_ATTEMPTS = 30       # 每IP最多尝试次数（演示用）
_LOGIN_WINDOW_SECONDS = 300    # 时间窗口（5分钟）

def _check_login_rate_limit(ip):
    """检查IP是否超出登录频率限制"""
    now = datetime.utcnow().timestamp()
    attempts = [t for t in _login_attempts.get(ip, []) if now - t < _LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    if len(attempts) >= _LOGIN_MAX_ATTEMPTS:
        return False
    _login_attempts[ip].append(now)
    return True

# Module-level singletons (lazy-initialised after app starts)
db = None
auth = None
emotion_analyzer = None
risk_alert = None
conversation_engine = None
prompt_manager = None
knowledge_base = None
rag_generator = None


def init_services(app):
    """Initialise all core service singletons. Call once inside create_app."""
    global db, auth, emotion_analyzer, risk_alert
    global conversation_engine, prompt_manager, knowledge_base, rag_generator

    # Database and auth always work (no API key needed)
    db = DatabaseManager()
    auth = AuthManager(db)

    try:
        emotion_analyzer = EmotionAnalyzer()
    except Exception as e:
        logger.warning("Emotion analyzer init skipped: %s", e)
        emotion_analyzer = None

    try:
        risk_alert = RiskAlertSystem()
    except Exception as e:
        logger.warning("Risk alert init skipped: %s", e)
        risk_alert = None

    try:
        prompt_manager = PromptManager()
    except Exception as e:
        logger.warning("Prompt manager init skipped: %s", e)
        prompt_manager = None

    # RAG modules need API key - skip if not configured
    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if api_key:
        try:
            knowledge_base = KnowledgeBaseManager()
            rag_generator = RAGGenerator()
        except Exception as e:
            logger.warning("RAG engine init skipped: %s", e)
            knowledge_base = None
            rag_generator = None
    else:
        knowledge_base = None
        rag_generator = None

    logger.info("Services initialized")

    # 后台预热真实情绪模型（emotion2vec + FER），避免实时调用首次卡顿
    try:
        import threading

        def _warm_up():
            try:
                from core.speech_emotion import get_speech_emotion_recognizer
                get_speech_emotion_recognizer()._ensure_model()
                logger.info("语音情绪模型(emotion2vec)预热完成")
            except Exception as e:  # noqa: BLE001
                logger.warning("语音情绪模型预热失败: %s", e)
            try:
                from core.yolo_emotion import get_detector
                detector = get_detector()
                detector._ensure_emotion_model()
                logger.info("人脸情绪模型预热完成 (face=%s, fer=%s)",
                            detector.face_model_kind, bool(detector.emotion_model))
            except Exception as e:  # noqa: BLE001
                logger.warning("人脸情绪模型预热失败: %s", e)

        threading.Thread(target=_warm_up, daemon=True).start()
    except Exception as e:  # noqa: BLE001
        logger.warning("模型预热启动失败: %s", e)

# ===================================================================
# Middleware / decorators
# ===================================================================

# ---- 1. JWT Authentication ------------------------------------------------

def auth_required(f):
    """要求有效的 JWT 令牌才能访问的装饰器。同时支持教师端和学生端 token。"""

    @wraps(f)
    def decorated(*args, **kwargs):
        token = None

        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            token = auth_header[7:]

        if not token:
            return jsonify({"success": False, "message": "未提供认证令牌，请先登录"}), 401

        try:
            payload = auth.verify_token(token)
        except Exception as exc:
            logger.warning("令牌验证失败: %s", exc)
            return jsonify({"success": False, "message": "令牌无效或已过期，请重新登录"}), 401

        if payload is None:
            return jsonify({"success": False, "message": "令牌无效或已过期"}), 401

        # 统一处理教师端和学生端 token
        if isinstance(payload, dict):
            g.user_type = payload.get("user_type", "staff")
            if g.user_type == "student":
                g.student_id = payload.get("student_id")
                g.student_id_str = payload.get("student_id_str")
                g.username = payload.get("name")
                g.role = "student"
                g.user_id = payload.get("student_id")
            else:
                g.user_id = payload.get("id") or payload.get("user_id")
                g.username = payload.get("username")
                g.role = payload.get("role")
                g.student_id = None
        else:
            g.user_id = getattr(payload, "id", None)
            g.username = getattr(payload, "username", None)
            g.role = getattr(payload, "role", None)
            g.user_type = "staff"
            g.student_id = None

        return f(*args, **kwargs)

    return decorated


# ---- 2. Role-Based Access Control -----------------------------------------

def role_required(allowed_roles):
    """角色鉴权装饰器，需与 @auth_required 配合使用。"""

    def decorator(f):
        @wraps(f)
        @auth_required
        def decorated(*args, **kwargs):
            current_role = getattr(g, "role", None)
            if current_role not in allowed_roles:
                return jsonify({
                    "success": False,
                    "message": "权限不足，您无权执行此操作",
                }), 403
            return f(*args, **kwargs)

        return decorated

    return decorator


# ---- 3. Automatic Operation Logging --------------------------------------

def log_action(action_name):
    """自动记录操作日志的装饰器。"""

    def decorator(f):
        @wraps(f)
        def decorated(*args, **kwargs):
            result = f(*args, **kwargs)
            try:
                username = getattr(g, "username", "unknown")
                logger.info("[%s] %s %s by %s", request.method, request.path, action_name, username)
            except Exception:
                pass
            return result

        return decorated

    return decorator


# ===================================================================
# Global Error Handlers
# ===================================================================

@api.errorhandler(401)
def handle_unauthorized(error):
    return jsonify({"success": False, "message": "未授权访问，请先登录"}), 401


@api.errorhandler(403)
def handle_forbidden(error):
    return jsonify({"success": False, "message": "禁止访问，权限不足"}), 403


@api.errorhandler(404)
def handle_not_found(error):
    return jsonify({"success": False, "message": "请求的资源不存在"}), 404


@api.errorhandler(500)
def handle_internal_error(error):
    logger.exception("服务器内部错误")
    return jsonify({"success": False, "message": "服务器内部错误，请稍后重试"}), 500

# ===================================================================
# 1. 认证路由 (Auth Routes)
# ===================================================================

@api.route("/auth/login", methods=["POST"])
def login():
    """用户登录，返回 JWT 令牌。"""
    ip = request.remote_addr or 'unknown'
    if not _check_login_rate_limit(ip):
        return jsonify({"success": False, "message": "登录尝试过于频繁，请5分钟后再试"}), 429
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效，请提供 JSON 数据"}), 400

    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"success": False, "message": "用户名和密码不能为空"}), 400

    try:
        user = auth.authenticate(username, password)
    except Exception as exc:
        logger.error("认证过程异常: %s", exc)
        return jsonify({"success": False, "message": "登录失败，请稍后重试"}), 500

    if user is None:
        return jsonify({"success": False, "message": "用户名或密码错误"}), 401

    token = auth.generate_token(user)

    return jsonify({
        "success": True,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": {
                "user_id": user.get("id"),
                "username": user.get("username"),
                "role": user.get("role"),
                "display_name": user.get("display_name"),
                "college": user.get("college"),
            },
        },
    }), 200


@api.route("/auth/logout", methods=["POST"])
@auth_required
@log_action("用户登出")
def logout():
    """注销当前令牌。"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None

    try:
        if token:
            auth.revoke_token(token)
    except Exception as exc:
        logger.error("令牌注销失败: %s", exc)

    return jsonify({"success": True, "message": "已成功退出登录"}), 200


# ===================================================================
# 学生登录 API
# ===================================================================

@api.route("/student/login", methods=["POST"])
def student_login():
    """学生登录，返回 JWT 令牌。"""
    ip = request.remote_addr or 'unknown'
    if not _check_login_rate_limit(ip):
        return jsonify({"success": False, "message": "登录尝试过于频繁，请5分钟后再试"}), 429
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效，请提供 JSON 数据"}), 400

    student_id = (data.get("student_id") or "").strip()
    password = (data.get("password") or "").strip()

    if not student_id or not password:
        return jsonify({"success": False, "message": "学号和密码不能为空"}), 400

    try:
        student = auth.authenticate_student(student_id, password)
    except Exception as exc:
        logger.error("学生认证过程异常: %s", exc)
        return jsonify({"success": False, "message": "登录失败，请稍后重试"}), 500

    if student is None:
        return jsonify({"success": False, "message": "学号或密码错误"}), 401

    token = auth.generate_student_token(student)

    return jsonify({
        "success": True,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": {
                "id": student.get("id"),
                "student_id": student.get("student_id"),
                "name": student.get("name"),
                "role": "student",
                "college": student.get("college"),
                "class_name": student.get("class_name"),
            },
        },
    }), 200


@api.route("/student/register", methods=["POST"])
def student_register():
    """学生注册（设置密码）"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效"}), 400

    student_id = (data.get("student_id") or "").strip()
    password = (data.get("password") or "").strip()
    name = (data.get("name") or "").strip()

    if not student_id or not password or not name:
        return jsonify({"success": False, "message": "学号、姓名和密码不能为空"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "message": "密码长度至少6位"}), 400

    # 检查学生是否存在
    student = db.get_student_by_student_id(student_id)
    if student is None:
        return jsonify({"success": False, "message": "学号不存在，请联系辅导员添加"}), 404

    if student.get("password_hash"):
        return jsonify({"success": False, "message": "该学号已注册，请直接登录"}), 400

    # 设置密码
    db.set_student_password(student["id"], password)

    # 生成token
    token = auth.generate_student_token(student)

    return jsonify({
        "success": True,
        "message": "注册成功",
        "data": {
            "token": token,
            "user": {
                "id": student.get("id"),
                "student_id": student.get("student_id"),
                "name": student.get("name"),
                "role": "student",
                "college": student.get("college"),
                "class_name": student.get("class_name"),
            },
        },
    }), 200


@api.route("/student/profile", methods=["GET"])
@auth_required
def get_student_profile():
    """获取学生个人信息"""
    if getattr(g, "user_type", "staff") != "student":
        return jsonify({"success": False, "message": "非学生用户"}), 403

    student = db.get_student_by_id(g.student_id)
    if student is None:
        return jsonify({"success": False, "message": "学生不存在"}), 404

    return jsonify({
        "success": True,
        "data": student,
    }), 200


# ===================================================================
# 即时通讯 API
# ===================================================================

@api.route("/messages/contacts", methods=["GET"])
@auth_required
def get_message_contacts():
    """获取消息联系人列表"""
    user_type = getattr(g, "user_type", "staff")
    if user_type == "student":
        user_id = g.student_id
    else:
        user_id = g.user_id

    contacts = db.get_message_contacts(user_id, user_type)

    return jsonify({
        "success": True,
        "data": contacts,
    }), 200


@api.route("/messages/<int:contact_id>", methods=["GET"])
@auth_required
def get_messages(contact_id):
    """获取与联系人的消息列表"""
    user_type = getattr(g, "user_type", "staff")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 50, type=int)

    if user_type == "student":
        student_id = g.student_id
        counselor_id = contact_id
        result = db.get_conversation_messages(student_id, counselor_id, page, per_page)
        db.mark_messages_read(student_id, counselor_id, "student")
    else:
        counselor_id = g.user_id
        student_id = contact_id
        result = db.get_conversation_messages(student_id, counselor_id, page, per_page)
        db.mark_messages_read(student_id, counselor_id, "counselor")

    return jsonify({
        "success": True,
        "data": result.get("items", []),
        "total": result.get("total", 0),
    }), 200


@api.route("/messages/send", methods=["POST"])
@auth_required
def send_message():
    """发送消息"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效"}), 400

    contact_id = data.get("contact_id")
    content = (data.get("content") or "").strip()
    message_type = data.get("message_type", "text")
    file_url = data.get("file_url")

    if not contact_id or not content:
        return jsonify({"success": False, "message": "联系人和消息内容不能为空"}), 400

    user_type = getattr(g, "user_type", "staff")

    if user_type == "student":
        student_id = g.student_id
        counselor_id = contact_id
        sender_type = "student"
        sender_id = student_id
    else:
        counselor_id = g.user_id
        student_id = contact_id
        sender_type = "counselor"
        sender_id = counselor_id

    msg_id = db.create_message(
        student_id=student_id,
        counselor_id=counselor_id,
        sender_type=sender_type,
        sender_id=sender_id,
        content=content,
        message_type=message_type,
        file_url=file_url,
    )

    return jsonify({
        "success": True,
        "data": {"id": msg_id},
    }), 200


@api.route("/messages/unread", methods=["GET"])
@auth_required
def get_unread_count():
    """获取未读消息数量"""
    user_type = getattr(g, "user_type", "staff")
    if user_type == "student":
        user_id = g.student_id
    else:
        user_id = g.user_id

    count = db.get_unread_count(user_id, user_type)

    return jsonify({
        "success": True,
        "data": {"unread_count": count},
    }), 200


@api.route("/messages/analyze-emotion", methods=["POST"])
@auth_required
def analyze_message_emotion():
    """分析消息文字中的情绪（核心功能：文字情绪检测）"""
    data = request.get_json(silent=True)
    if not data or not data.get("text"):
        return jsonify({"success": False, "message": "请提供要分析的文本"}), 400

    text = data["text"].strip()
    if len(text) < 2:
        return jsonify({"success": True, "data": {"emotion": "正常", "risk": "low", "intensity": 1}}), 200

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        # 本地关键词匹配作为后备
        return jsonify({"success": True, "data": _local_text_emotion(text)}), 200

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        system_prompt = (
            'You are a mental health emotion analysis expert. Analyze the text emotion '
            'and return strictly as JSON: {"emotion":"type","risk":"low/medium/high",'
            '"intensity":1-10,"keywords":["word1"],"suggestion":"brief advice"}. '
            'Emotion types: neutral,happy,down,anxious,irritated,depressed,angry,fearful,sad,nervous.'
        )
        resp = client.chat.completions.create(
            model="qwen-turbo",
            messages=[{"role": "system", "content": system_prompt},
                      {"role": "user", "content": text}],
            max_tokens=200, temperature=0.1
        )
        result_text = resp.choices[0].message.content.strip()
        import re, json
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if match:
            result = json.loads(match.group())
            # Map English emotion names back to Chinese
            en_map = {"neutral":"正常","happy":"高兴","down":"低落","anxious":"焦虑",
                      "irritated":"烦躁","depressed":"压抑","angry":"愤怒",
                      "fearful":"恐惧","sad":"悲伤","nervous":"紧张"}
            if result.get("emotion","") in en_map:
                result["emotion"] = en_map[result["emotion"]]
        else:
            result = {"emotion": "正常", "risk": "low", "intensity": 1, "keywords": [], "suggestion": ""}
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.warning("文字情绪分析失败: %s", e)
        return jsonify({"success": True, "data": _local_text_emotion(text)}), 200


def _local_text_emotion(text):
    """本地关键词情绪分析（无需API）"""
    keywords = {
        "焦虑": ["焦虑", "担心", "紧张", "不安", "压力", "崩溃", "受不了"],
        "悲伤": ["难过", "伤心", "哭了", "失去", "痛苦", "绝望", "想死", "自杀"],
        "愤怒": ["生气", "愤怒", "讨厌", "恨", "不公平", "凭什么", "滚"],
        "恐惧": ["害怕", "恐惧", "恐怖", "吓", "噩梦", "不敢"],
        "压抑": ["压抑", "憋着", "没人理解", "孤独", "寂寞", "一个人"],
        "低落": ["低落", "没意思", "无聊", "懒得", "不想动", "好累", "没劲"],
        "高兴": ["开心", "高兴", "哈哈", "太好了", "棒", "喜欢", "谢谢老师"],
        "正常": ["好的", "收到", "知道", "嗯", "谢谢"],
    }
    scores = {}
    for emotion, words in keywords.items():
        score = sum(1 for w in words if w in text)
        if score > 0:
            scores[emotion] = score
    if not scores:
        return {"emotion": "正常", "risk": "low", "intensity": 1, "keywords": [], "suggestion": ""}
    top = max(scores, key=scores.get)
    risk = "high" if top in ("悲伤","恐惧","压抑") and scores[top] >= 2 else ("medium" if top in ("焦虑","愤怒","低落") else "low")
    intensity = min(10, scores[top] * 3 + 2)
    return {"emotion": top, "risk": risk, "intensity": intensity, "keywords": [], "suggestion": "建议关注学生情绪状态" if risk != "low" else ""}


def _fallback_knowledge_search(query, top_k=5):
    """知识库搜索后备：基于jieba关键词的本地文档匹配（无需ChromaDB）"""
    import jieba, os, re
    docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
    query_words = set(jieba.lcut_for_search(query.lower()))
    results = []
    if os.path.isdir(docs_dir):
        for fname in os.listdir(docs_dir):
            fpath = os.path.join(docs_dir, fname)
            if not os.path.isfile(fpath): continue
            try:
                with open(fpath, "r", encoding="utf-8", errors="ignore") as f:
                    content = f.read()
            except Exception:
                continue
            # 简单TF匹配
            content_words = set(jieba.lcut_for_search(content.lower()))
            score = len(query_words & content_words) / max(len(query_words), 1)
            if score > 0.05:
                # 提取匹配片段
                snippet = content[:300]
                for w in query_words:
                    idx = content.lower().find(w.lower())
                    if idx > 0:
                        start = max(0, idx - 80)
                        snippet = "..." + content[start:start+300] + "..."
                        break
                results.append({
                    "doc_id": fname, "score": round(score, 3),
                    "content": content[:500],
                    "snippet": snippet,
                    "source": fname
                })
    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:top_k] or [{"doc_id": "无匹配", "score": 0, "content": "知识库中暂无与您搜索相关的内容", "snippet": "请先上传相关文档到知识库", "source": "system"}]


# 心理专家级话术推荐：话术分类元信息（icon/颜色/定位）
GUIDANCE_CATEGORY_META = [
    {"type": "共情安抚", "icon": "💗", "color": "#ec4899",
     "description": "先接住情绪，让学生感到被理解、被看见"},
    {"type": "开放式提问", "icon": "❓", "color": "#3b82f6",
     "description": "用开放式问题引导倾诉，避免「是/否」式封闭回答"},
    {"type": "积极引导", "icon": "🌱", "color": "#10b981",
     "description": "从积极视角重构问题，激发学生自身力量"},
    {"type": "资源支持", "icon": "🤝", "color": "#8b5cf6",
     "description": "提供具体、可获得的资源与行动路径"},
    {"type": "危机干预", "icon": "🚨", "color": "#ef4444",
     "description": "高风险情境下的安全确认与即时干预"},
]

# 各情绪类型的关键词，用于本地兜底话术生成（无 API Key 时）
GUIDANCE_EMOTION_KEYWORDS = {
    "悲伤": ["难过", "伤心", "哭", "失去", "痛苦", "绝望", "想死", "自杀", "活不下去", "没意思"],
    "焦虑": ["焦虑", "担心", "紧张", "不安", "压力", "崩溃", "受不了", "害怕考", "挂科"],
    "愤怒": ["生气", "愤怒", "讨厌", "恨", "不公平", "凭什么", "吵架", "闹矛盾"],
    "恐惧": ["害怕", "恐惧", "噩梦", "不敢", "吓"],
    "压抑": ["压抑", "憋着", "没人理解", "孤独", "寂寞", "一个人", "提不起兴趣"],
    "低落": ["低落", "无聊", "懒得", "不想动", "好累", "没劲", "失眠", "睡不好"],
    "烦躁": ["烦", "烦躁", "受够", "吵", "打扰"],
    "紧张": ["紧张", "发抖", "心跳", "慌"],
    "高兴": ["开心", "高兴", "太好了", "棒", "喜欢", "谢谢老师"],
}

# 兜底话术库：key = 情绪，value = 5 类话术各 1~2 条
GUIDANCE_FALLBACK_SCRIPTS = {
    "共情安抚": {
        "default": [
            "我能感受到你现在很不容易，谢谢你愿意把这些告诉我。",
            "换作是我处在你这个位置，可能也会有类似的感受，这很正常。",
        ],
        "悲伤": ["听起来你心里积压了很多委屈和难过，能说出来真的很勇敢。", "你不是一个人在面对，我在这里陪着你。"],
        "焦虑": ["压力这么大，会焦虑是很自然的反应，我们先一起把它拆开看看。", "先别急着逼自己，一步一步来，你已经做得很好了。"],
        "愤怒": ["我能理解你的生气，这种情绪本身没有错，我们先别被它带着走。", "谢谢你没有憋在心里，而是选择说出来。"],
        "恐惧": ["害怕是身体在保护你，我们一起看看这份恐惧背后是什么。", "不用一个人扛，说出来会轻松一些。"],
        "压抑": ["你承受的比表面看到的多得多，辛苦你了。", "能感到孤独和压抑，恰恰说明你很在意，也很敏感。"],
        "低落": ["最近一定很累吧，允许自己慢下来，这不丢人。", "状态不好没关系，我们一点点来。"],
        "烦躁": ["最近是不是有什么事情一直让你心里堵得慌？", "烦躁背后通常藏着某种没被满足的需要，我们聊聊。"],
        "紧张": ["紧张说明你在乎这件事，这是好事。", "深呼吸，我们慢慢说，不着急。"],
    },
    "开放式提问": {
        "default": [
            "能和我说说，最近是什么时候开始有这种感觉的吗？",
            "如果用一个词形容现在的状态，你会想到什么？",
        ],
        "悲伤": ["这种难过的感觉，一般在什么情况下会特别强烈？", "你希望身边的人怎么帮你，才会感觉好一点？"],
        "焦虑": ["如果把这个压力分成十份，你觉得最让你喘不过气的是哪一部分？", "过去有没有哪次，你成功扛过类似的情况？"],
        "愤怒": ["这件事里，最让你接受不了的是哪一点？", "如果对方现在就在你面前，你最想对他说什么？"],
        "恐惧": ["你害怕的具体是什么？是结果，还是过程中的某个环节？", "如果最坏的情况发生了，你觉得自己能承受吗？"],
        "压抑": ["你感觉最不被理解的地方是什么？", "有没有一个人，是你愿意多说两句的？"],
        "低落": ["这种提不起劲的状态，持续了多久了？", "有没有哪一刻，你觉得自己稍微轻松了一点？"],
        "烦躁": ["最近哪件事最让你心烦？", "你觉得是什么让这种烦躁感一直消不掉？"],
        "紧张": ["你紧张的具体是什么场合？", "如果紧张程度从 1 到 10，你给自己打几分？"],
    },
    "积极引导": {
        "default": [
            "其实你已经迈出了求助这一步，这本身就是一种力量。",
            "我们先把能控制的事做好，剩下的交给时间。",
        ],
        "悲伤": ["你愿意说出来，说明你内心依然渴望被理解、渴望变好。", "难过会过去的，但这段时间我会一直支持你。"],
        "焦虑": ["你担心，说明你有责任心、想把事情做好，这是你的优点。", "把大目标切成小步，每完成一步都是进步。"],
        "愤怒": ["能把情绪说出来而不是憋着或爆发，你已经在用更成熟的方式处理了。", "你的底线和感受值得被尊重。"],
        "恐惧": ["恐惧的反面不是勇敢，而是行动。我们找一个最小的第一步试试。", "你已经面对了很多人会选择逃避的事，这很了不起。"],
        "压抑": ["你比你以为的更有韧性，能走到现在就是证明。", "表达出来的那一刻，你就已经在治愈自己了。"],
        "低落": ["情绪有起伏是正常的，低谷里也能慢慢积攒力气。", "今天能来和我说这些，本身就是一件值得肯定的事。"],
        "烦躁": ["你能敏锐地察觉到自己的烦躁，这是自我觉察的第一步。", "把烦躁的事一件件理清，你会发现没想象中那么难。"],
        "紧张": ["适度的紧张能帮你发挥得更好，关键是别让它失控。", "你已经准备了，剩下的就是相信自己。"],
    },
    "资源支持": {
        "default": [
            "学校心理中心有专业咨询师，我可以帮你预约，全程保密。",
            "这个学期学习上有困难，我可以帮你联系学习委员或学长学姐。",
        ],
        "悲伤": ["我建议你近期去心理中心找专业老师聊聊，我可以陪你去。", "如果需要，我可以和你的任课老师沟通，适当调整学习节奏。"],
        "焦虑": ["关于这门课，我帮你约一下任课老师，梳理一下重点。", "学校有学业辅导小组，我帮你对接一个。"],
        "愤怒": ["如果涉及人际冲突，我可以先和对方/室友聊聊，帮你协调。", "需要的话我们可以一起定个规则或方案，把问题解决掉。"],
        "恐惧": ["心理中心的老师处理过很多类似的情况，经验很丰富。", "我会在接下来的时间里多关注你的状态，你随时可以来找我。"],
        "压抑": ["心理中心的咨询完全保密，你可以放心去聊。", "多参加一点集体活动，我可以帮你推荐适合的社团。"],
        "低落": ["睡眠和饮食如果持续不好，我陪你去校医院看看。", "心理中心的咨询时段我可以帮你优先预约。"],
        "烦躁": ["把烦心事列出来，我们一起分个优先级，一件件处理。", "如果环境太吵影响你，我可以帮你协调宿舍或自习空间。"],
        "紧张": ["我可以帮你做一些放松训练，或者推荐你听一些减压音频。", "考前我们可以约一次模拟，帮你熟悉流程降低紧张。"],
    },
    "危机干预": {
        "default": [
            "我很担心你的安全，我们先确保你现在是安全的，好吗？",
            "你现在的感受非常重要，我会一直陪着你，不会让你一个人面对。",
        ],
        "悲伤": ["关于你提到的伤害自己的想法，我需要确认一下：你现在安全吗？", "我们先不谈别的，先确认你此刻是安全的，这比什么都重要。"],
        "恐惧": ["如果你感到非常害怕或难以承受，我们一起去心理中心找专业老师，现在就可以。"],
        "压抑": ["你一个人扛了这么久，我很心疼。接下来的事我们一起来想办法，好吗？"],
    },
}


def _local_guidance(conversation_text, student_name="学生"):
    """本地兜底话术生成：基于情绪关键词，产出多类型心理专家级话术（无需 API）。"""
    emotion = "default"
    best_score = 0
    for emo, words in GUIDANCE_EMOTION_KEYWORDS.items():
        score = sum(1 for w in words if w in conversation_text)
        if score > best_score:
            best_score = score
            emotion = emo
    if best_score == 0:
        emotion = "default"

    emo_label = "正常" if emotion == "default" else emotion
    # 情绪评估一句话
    assessment_map = {
        "悲伤": f"从对话看，{student_name} 情绪偏低落，可能存在悲伤或无助的感受，需优先共情与安全确认。",
        "焦虑": f"从对话看，{student_name} 表现出明显的焦虑与压力，需先缓解紧张、再逐层拆解压力来源。",
        "愤怒": f"从对话看，{student_name} 有较强的愤怒或不公平感，需先承接情绪、再引导理性表达。",
        "恐惧": f"从对话看，{student_name} 存在恐惧或回避情绪，需营造安全感、逐步澄清恐惧对象。",
        "压抑": f"从对话看，{student_name} 情绪较为压抑，可能长期独自承受，需耐心引导其表达。",
        "低落": f"从对话看，{student_name} 状态偏低落、动力不足，需温和陪伴并关注睡眠饮食。",
        "烦躁": f"从对话看，{student_name} 有些烦躁不安，需帮助其梳理具体困扰。",
        "紧张": f"从对话看，{student_name} 较为紧张，需通过放松与具体化降低紧张感。",
        "default": f"从对话看，{student_name} 整体状态尚可，可正常沟通并给予适度支持。",
    }

    categories = []
    tips = []
    high_risk = emotion in ("悲伤", "恐惧") and any(
        w in conversation_text for w in ["想死", "自杀", "活不下去", "伤害自己"]
    )
    for meta in GUIDANCE_CATEGORY_META:
        ctype = meta["type"]
        scripts = GUIDANCE_FALLBACK_SCRIPTS[ctype]
        # 危机干预仅在高风险时展示
        if ctype == "危机干预" and not high_risk:
            continue
        pool = scripts.get(emotion) or scripts.get("default") or []
        if not pool:
            continue
        categories.append({
            "type": ctype,
            "icon": meta["icon"],
            "color": meta["color"],
            "description": meta["description"],
            "scripts": pool,
        })
        tips.extend(pool[:1])

    return {
        "emotion_assessment": assessment_map.get(emotion, assessment_map["default"]),
        "risk_alert": "建议预警" if high_risk else ("建议关注" if emotion in ("悲伤", "焦虑", "压抑", "恐惧") else "无风险"),
        "categories": categories,
        "communication_tips": tips[:3] if tips else ["先倾听学生的感受，再逐步引导。"],
        "counseling_plan": "先建立信任与安全感，通过共情稳定情绪；再开放式提问澄清问题；最后结合资源支持给出可执行建议。",
        "source": "local",
    }


@api.route("/messages/counselor-guidance", methods=["POST"])
@auth_required
def counselor_guidance():
    """AI辅导助手：分析学生对话，输出多类型心理专家级沟通话术（可点击填入聊天框）。"""
    data = request.get_json(silent=True)
    if not data or not data.get("messages"):
        return jsonify({"success": False, "message": "请提供对话内容"}), 400

    messages = data["messages"]
    student_name = data.get("student_name", "学生")
    conversation_text = "\n".join([
        ("学生" if m.get("sender_type") == "student" else "老师") + "：" + m.get("content", "")
        for m in messages[-10:]  # 最近10条
    ])

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200

    # 构建分类话术的输出说明，供模型严格遵循
    category_spec = "、".join([
        '{"type":"%s","icon":"%s","scripts":["可直接发送的话术1","话术2","话术3"]}'
        % (m["type"], m["icon"]) for m in GUIDANCE_CATEGORY_META
    ])

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        prompt = (
            f"你是高校心理辅导专家。以下是辅导员与{student_name}的对话记录，请分析并给出可落地的辅导话术。\n\n"
            f"对话记录：\n{conversation_text}\n\n"
            f"请严格返回 JSON（不要输出任何多余文字）：\n"
            f'{{\n'
            f'  "emotion_assessment":"学生当前情绪评估（1-2句话）",\n'
            f'  "risk_alert":"无风险 / 建议关注 / 建议预警（三选一）",\n'
            f'  "categories":[\n'
            f'    {category_spec}\n'
            f'  ]\n'
            f'}}\n\n'
            f"要求：\n"
            f"1. categories 必须包含上述 5 个分类，每个分类 2~4 条「可直接发送」的话术；\n"
            f"2. 话术要具体、温和、专业，符合心理咨询伦理，避免说教与评判；\n"
            f"3. 若学生无自伤/自杀风险，「危机干预」分类改为安全与支持性话术。"
        )
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1200, temperature=0.4
        )
        result_text = resp.choices[0].message.content.strip()
        import re, json
        match = re.search(r'\{.*\}', result_text, re.DOTALL)
        if not match:
            return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200
        result = json.loads(match.group())
        # 归一化：补齐分类元信息 icon/color，并把 scripts 洗成列表
        meta_by_type = {m["type"]: m for m in GUIDANCE_CATEGORY_META}
        categories = []
        for cat in result.get("categories", []) or []:
            if not isinstance(cat, dict):
                continue
            ctype = cat.get("type", "")
            scripts = cat.get("scripts", [])
            if isinstance(scripts, str):
                scripts = [scripts]
            scripts = [str(s).strip() for s in scripts if str(s).strip()]
            if not ctype or not scripts:
                continue
            meta = meta_by_type.get(ctype, {})
            categories.append({
                "type": ctype,
                "icon": cat.get("icon") or meta.get("icon", "💬"),
                "color": meta.get("color", "#6366f1"),
                "description": meta.get("description", ""),
                "scripts": scripts,
            })
        tips = []
        for cat in categories:
            tips.extend(cat["scripts"][:1])
        if not categories:
            # 模型返回异常时兜底
            return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200
        result["categories"] = categories
        result["communication_tips"] = result.get("communication_tips") or tips[:3]
        result["counseling_plan"] = result.get("counseling_plan") or "先共情稳定情绪，再开放式提问澄清，最后给出资源支持与可执行建议。"
        result["source"] = "ai"
        return jsonify({"success": True, "data": result}), 200
    except Exception as e:
        logger.error("辅导分析失败: %s", e)
        return jsonify({"success": True, "data": _local_guidance(conversation_text, student_name)}), 200


# ===================================================================
# 预约 API
# ===================================================================

@api.route("/appointments", methods=["GET"])
@auth_required
def get_appointments():
    """获取预约列表"""
    user_type = getattr(g, "user_type", "staff")
    if user_type == "student":
        user_id = g.student_id
    else:
        user_id = g.user_id

    status = request.args.get("status")
    page = request.args.get("page", 1, type=int)
    per_page = request.args.get("per_page", 20, type=int)

    result = db.get_appointments(user_id, user_type, status, page, per_page)

    return jsonify({
        "success": True,
        "data": result.get("items", []),
        "total": result.get("total", 0),
    }), 200


@api.route("/appointments/create", methods=["POST"])
@auth_required
def create_appointment():
    """创建预约"""
    if getattr(g, "user_type", "staff") != "student":
        return jsonify({"success": False, "message": "仅学生可创建预约"}), 403

    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效"}), 400

    student_id = g.student_id
    counselor_id = data.get("counselor_id")
    appointment_time = data.get("appointment_time")
    reason = data.get("reason", "")
    duration = data.get("duration", 30)

    if not counselor_id or not appointment_time:
        return jsonify({"success": False, "message": "辅导员和预约时间不能为空"}), 400

    try:
        appt_time = datetime.fromisoformat(appointment_time.replace('Z', '+00:00'))
    except:
        return jsonify({"success": False, "message": "时间格式无效"}), 400

    appt_id = db.create_appointment(student_id, counselor_id, appt_time, reason, duration)

    return jsonify({
        "success": True,
        "message": "预约创建成功",
        "data": {"id": appt_id},
    }), 200


@api.route("/appointments/<int:appt_id>/status", methods=["PUT"])
@auth_required
def update_appointment_status(appt_id):
    """更新预约状态"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效"}), 400

    status = data.get("status")
    notes = data.get("notes")

    if status not in ["pending", "confirmed", "completed", "cancelled"]:
        return jsonify({"success": False, "message": "无效的状态"}), 400

    db.update_appointment_status(appt_id, status, notes)

    return jsonify({
        "success": True,
        "message": "预约状态已更新",
    }), 200


@api.route("/auth/profile", methods=["GET"])
@auth_required
@log_action("查看个人信息")
def get_profile():
    """获取当前登录用户的详细信息。"""
    try:
        user = auth.get_user(g.user_id)
        if user is None:
            return jsonify({"success": False, "message": "用户不存在"}), 404
        return jsonify({
            "success": True,
            "data": {
                "user_id": user.get("id"),
                "username": user.get("username"),
                "display_name": user.get("display_name"),
                "role": user.get("role"),
                "college": user.get("college"),
                "class_name": user.get("class_name"),
                "email": user.get("email"),
                "phone": user.get("phone"),
                "created_at": user.get("created_at"),
            },
        }), 200
    except Exception as exc:
        logger.error("获取用户信息失败: %s", exc)
        return jsonify({"success": False, "message": "获取用户信息失败"}), 500


@api.route("/auth/profile", methods=["PUT"])
@auth_required
@log_action("更新个人信息")
def update_profile():
    """更新当前用户的个人资料。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效，请提供 JSON 数据"}), 400

    allowed_fields = {"name", "email", "phone", "college", "class_name"}
    updates = {k: v for k, v in data.items() if k in allowed_fields and v is not None}

    if not updates:
        return jsonify({"success": False, "message": "没有可更新的字段"}), 400

    try:
        auth.update_user(g.user_id, updates)
        return jsonify({"success": True, "message": "个人资料更新成功"}), 200
    except Exception as exc:
        logger.error("更新用户信息失败: %s", exc)
        return jsonify({"success": False, "message": "更新失败，请稍后重试"}), 500

# ===================================================================
# 2. 会话管理路由 (Conversation Routes)
# ===================================================================

@api.route("/conversation/organize", methods=["POST"])
@auth_required
@log_action("整理会话记录")
def organize_conversation():
    """将原始会话内容整理为结构化记录。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供原始会话内容"}), 400

    raw_content = data.get("content") or data.get("raw_content")
    if not raw_content:
        return jsonify({"success": False, "message": "会话内容不能为空"}), 400

    scene = data.get("scene", "谈心记录")

    api_key = os.environ.get("DASHSCOPE_API_KEY", "")
    if not api_key:
        return jsonify({"success": False, "message": "API密钥未配置"}), 500

    scene_prompts = {
        "谈心记录": """你是一位资深高校辅导员助手。请将以下对话内容整理为标准的谈心谈话记录。

请严格按照以下格式输出（使用Markdown格式）：

## 谈心谈话记录

| 项目 | 内容 |
|------|------|
| **时间** | （根据内容推断合理时间） |
| **地点** | （根据内容推断） |
| **谈话人** | （辅导员姓名，可写XXX） |
| **谈话对象** | （学生姓名，可写XXX） |
| **谈话主题** | （提炼核心主题） |

### 一、谈话背景
（简要说明谈话的起因和背景）

### 二、谈话主要内容
（用问答形式整理对话要点，条理清晰）

### 三、学生思想与情绪状态评估
（根据对话判断学生的心理状态、情绪变化）

### 四、发现的主要问题
- （问题1）
- （问题2）

### 五、后续跟进措施
- （具体措施1，含时间节点）
- （具体措施2，含时间节点）
- （具体措施3）

请确保内容真实客观，语言专业温和。""",

        "班会策划": """你是一位经验丰富的高校辅导员，请根据主题策划一次主题班会方案。

请严格按照以下格式输出（使用Markdown格式）：

# 主题班会策划方案

## 一、班会基本信息

| 项目 | 内容 |
|------|------|
| **班会主题** | （根据用户输入确定） |
| **班会时间** | 建议45-60分钟 |
| **班会地点** | XX教室 |
| **参加人员** | XX学院XX级全体学生 |
| **主持人** | XXX（辅导员/学生干部） |

## 二、班会目标

1. **知识目标**：（学生应了解的知识点）
2. **能力目标**：（学生应提升的能力）
3. **情感目标**：（学生应形成的态度和价值观）

## 三、班会准备

1. 前期准备：
   - （准备工作1）
   - （准备工作2）
2. 所需材料：
   - （材料清单）
3. 人员分工：
   - （分工安排）

## 四、班会流程

### 第一环节：导入（约5分钟）
- 具体内容和方式

### 第二环节：主体活动（约30分钟）
- 活动一：（名称）
  - 目的、方式、时间
- 活动二：（名称）
  - 目的、方式、时间

### 第三环节：讨论分享（约10分钟）
- 讨论题目和分享方式

### 第四环节：总结升华（约5分钟）
- 辅导员总结要点

## 五、预期效果

（描述预期达到的教育效果）

## 六、注意事项

1. （注意事项1）
2. （注意事项2）
3. （注意事项3）

请确保方案具有可操作性，活动设计贴近学生实际。""",

        "公文写作": """你是高校行政公文写作助手。请按照GB/T 9704国家标准格式起草公文。

请严格按照以下格式输出（使用Markdown格式）：

# 关于XXXX的通知

各学院、各部门：

## 一、背景与目的
（说明发文背景和目的）

## 二、工作安排

### （一）时间安排
- （时间节点1）
- （时间节点2）

### （二）工作内容
1. （内容1）
2. （内容2）

### （三）具体要求
1. （要求1）
2. （要求2）

## 三、联系方式

联系人：XXX
联系电话：XXX
邮箱：XXX

---

**XX大学学生工作处**
**2024年X月X日**

请确保用语准确、简洁、庄重，符合行政公文规范。""",

        "情绪分析": """你是专业的心理咨询分析助手。请分析以下文本中的情绪状态。

请严格按照以下格式输出（使用Markdown格式）：

## 情绪分析报告

### 一、情绪识别

| 情绪类型 | 强度 | 依据 |
|----------|------|------|
| （主要情绪） | 高/中/低 | （文本中的具体表达） |
| （次要情绪） | 高/中/低 | （文本中的具体表达） |

### 二、关键风险信号
- （信号1：具体文本片段）
- （信号2：具体文本片段）

### 三、风险评估
- **风险等级**：高/中/低
- **判断依据**：（具体说明）
- **是否需要启动危机干预**：是/否

### 四、建议措施
1. （辅导员应采取的具体行动1）
2. （辅导员应采取的具体行动2）
3. （辅导员应采取的具体行动3）

### 五、后续关注要点
- （需要持续观察的方面）

请保持专业、客观、温和的分析态度。""",

        "请假审批": """你是高校学工处处理助手，负责协助辅导员处理学生请假审批。

请严格按照以下格式输出（使用Markdown格式）：

## 请假审批意见

### 一、学生信息
| 项目 | 内容 |
|------|------|
| **姓名** | XXX |
| **班级** | XX学院XX班 |
| **请假类型** | 事假/病假/公假 |
| **请假时间** | X月X日至X月X日（共X天） |

### 二、请假理由
（根据学生描述整理）

### 三、审批建议
- **建议结果**：批准/暂缓/不予批准
- **审批理由**：（具体说明）

### 四、注意事项
1. （提醒事项1）
2. （提醒事项2）
3. （相关跟进安排）

请根据学校规定给出合理建议。""",
    }

    system_msg = scene_prompts.get(scene, "你是高校辅导员助手。请整理以下内容。")

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")
        resp = client.chat.completions.create(
            model="qwen-plus",
            messages=[
                {"role": "system", "content": system_msg},
                {"role": "user", "content": raw_content}
            ],
            temperature=0.7,
            max_tokens=3000
        )
        result = resp.choices[0].message.content
        return jsonify({"success": True, "message": "整理完成", "content": result}), 200
    except Exception as exc:
        logger.error("整理失败: %s", exc)
        return jsonify({"success": False, "message": "整理失败: " + "内部错误，请稍后重试"}), 500



@api.route("/conversation/recognize-image", methods=["POST"])
@auth_required
def recognize_image():
    """识别聊天记录截图，提取对话内容并整理为谈心记录。"""
    if "image" not in request.files:
        return jsonify({"success": False, "message": "请上传图片"}), 400

    image_file = request.files["image"]
    if not image_file.filename:
        return jsonify({"success": False, "message": "文件名为空"}), 400

    allowed_ext = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".bmp"}
    ext = os.path.splitext(image_file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({"success": False, "message": "仅支持jpg/png/gif/webp格式"}), 400

    try:
        # Read image and convert to base64
        import base64
        image_bytes = image_file.read()
        image_b64 = base64.b64encode(image_bytes).decode("utf-8")

        # Determine MIME type
        mime_map = {".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
                     ".gif": "image/gif", ".webp": "image/webp", ".bmp": "image/bmp"}
        mime_type = mime_map.get(ext, "image/jpeg")

        api_key = os.environ.get("DASHSCOPE_API_KEY", "")
        if not api_key:
            return jsonify({"success": False, "message": "API密钥未配置"}), 500

        from openai import OpenAI
        client = OpenAI(api_key=api_key, base_url="https://dashscope.aliyuncs.com/compatible-mode/v1")

        # Use qwen-vl-plus for image recognition
        resp = client.chat.completions.create(
            model="qwen-vl-plus",
            messages=[
                {
                    "role": "system",
                    "content": """你是一位高校辅导员助手。请完成以下两步：

第一步：识别图片中的聊天记录，提取出所有对话内容，按照“发言人：内容”的格式整理。

第二步：将识别出的对话内容整理为标准的谈心谈话记录格式：

## 谈心谈话记录

| 项目 | 内容 |
|------|------|
| **时间** | 根据图片中的时间戳填写 |
| **地点** | 根据内容推断 |
| **谈话人** | 辅导员 |
| **谈话对象** | 学生姓名 |
| **谈话主题** | 提炼核心主题 |

### 一、谈话背景
(简要说明谈话起因)

### 二、谈话主要内容
(用问答形式整理对话要点)

### 三、学生思想与情绪状态评估
(根据对话判断学生心理状态)

### 四、发现的主要问题
- (问题1)
- (问题2)

### 五、后续跟进措施
- (具体措施1，含时间节点)
- (具体措施2)

如果图片中的内容不是聊天记录，则说明图片内容并尝试了解其含义。"""
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:{mime_type};base64,{image_b64}"}
                        },
                        {"type": "text", "text": "请识别这张聊天记录截图，提取对话内容并整理为标准的谈心谈话记录。"}
                    ]
                }
            ],
            max_tokens=3000
        )

        result = resp.choices[0].message.content
        return jsonify({"success": True, "message": "图片识别完成", "content": result}), 200

    except Exception as exc:
        logger.error("图片识别失败: %s", exc)
        return jsonify({"success": False, "message": "图片识别失败: " + "内部错误，请稍后重试"}), 500


@api.route("/conversation/upload-document", methods=["POST"])
@auth_required
@log_action("上传文档识别")
def upload_document():
    """上传文档（PDF/Word/文本等），提取内容并用AI整理为谈心记录。"""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "请上传文件", "content": "请上传文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "message": "文件名为空", "content": "文件名为空"}), 400

    ext = os.path.splitext(file.filename)[1].lower()
    allowed = {".pdf", ".doc", ".docx", ".txt", ".md", ".csv", ".xls", ".xlsx"}
    if ext not in allowed:
        return jsonify({"success": False, "message": f"不支持的文件格式: {ext}", "content": f"不支持的文件格式: {ext}，支持: {', '.join(allowed)}"}), 400

    try:
        content_text = ""
        if ext in (".txt", ".md", ".csv"):
            content_text = file.read().decode("utf-8", errors="ignore")
        elif ext == ".pdf":
            try:
                import pdfplumber
                with pdfplumber.open(file) as pdf:
                    for page in pdf.pages:
                        t = page.extract_text()
                        if t:
                            content_text += t + "\n"
            except ImportError:
                content_text = "[PDF文件已上传，但服务器未安装pdfplumber库]"
        elif ext in (".doc", ".docx"):
            try:
                import docx
                doc = docx.Document(file)
                content_text = "\n".join([p.text for p in doc.paragraphs if p.text.strip()])
            except ImportError:
                content_text = "[Word文件已上传，但服务器未安装python-docx库]"
        elif ext in (".xls", ".xlsx"):
            content_text = "[Excel文件已上传]"
        else:
            content_text = file.read().decode("utf-8", errors="ignore")

        if not content_text.strip():
            content_text = f"[文件 {file.filename} 已上传，但未能提取到有效文本内容]"

        if len(content_text) > 5000:
            content_text = content_text[:5000] + "\n\n[内容已截断，共" + str(len(content_text)) + "字]"

        organized = ""
        api_key = config["llm"].DASHSCOPE_API_KEY
        if api_key and conversation_engine:
            try:
                reply = conversation_engine.chat(
                    scene="谈心记录",
                    user_message=f"以下是上传的文档内容（{file.filename}），请整理为谈心记录：\n\n{content_text}"
                )
                organized = reply
            except Exception as e:
                logger.warning("LLM organize failed: %s", e)

        if not organized:
            organized = f"## 文档内容摘要 - {file.filename}\n\n{content_text[:2000]}\n\n---\n*提示：配置API密钥后可AI自动整理为结构化谈心记录*"

        return jsonify({
            "success": True,
            "content": organized,
            "message": f"文档 {file.filename} 已识别",
            "filename": file.filename,
            "raw_content": content_text[:500],
        }), 200

    except Exception as exc:
        logger.error("upload_document error: %s", exc)
        return jsonify({"success": False, "message": f"文件处理失败: {exc}", "content": f"文件处理失败: {exc}"}), 500

@api.route("/conversation/list", methods=["GET"])
@auth_required
@log_action("查看会话列表")
def list_conversations():
    """分页获取会话列表，支持按学院、日期、状态等过滤。"""
    try:
        filters = {
            "college": request.args.get("college"),
            "status": request.args.get("status"),
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
            "student_name": request.args.get("student_name"),
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

        result = db.search_conversations(
            filters=filters,
            page=page,
            per_page=per_page,
            user_id=g.user_id,
            role=g.role,
        )

        return jsonify({
            "success": True,
            "data": result.get("items", []),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": result.get("total", 0),
                "total_pages": result.get("total_pages", 0),
            },
        }), 200
    except Exception as exc:
        logger.error("获取会话列表失败: %s", exc)
        return jsonify({"success": False, "message": "获取会话列表失败"}), 500


@api.route("/conversation/<int:conversation_id>", methods=["GET"])
@auth_required
@log_action("查看会话详情")
def get_conversation(conversation_id):
    """获取单条会话的完整信息。"""
    try:
        conversation = db.get_conversation(conversation_id)
        if conversation is None:
            return jsonify({"success": False, "message": "会话记录不存在"}), 404
        return jsonify({"success": True, "data": conversation}), 200
    except Exception as exc:
        logger.error("获取会话详情失败: %s", exc)
        return jsonify({"success": False, "message": "获取会话详情失败"}), 500


@api.route("/conversation/<int:conversation_id>", methods=["PUT"])
@auth_required
@log_action("更新会话记录")
def update_conversation(conversation_id):
    """更新会话记录信息。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供要更新的字段"}), 400

    allowed_fields = {
        "status", "summary", "notes", "tags",
        "risk_level", "follow_up_needed", "follow_up_date",
    }
    updates = {k: v for k, v in data.items() if k in allowed_fields and v is not None}

    if not updates:
        return jsonify({"success": False, "message": "没有可更新的字段"}), 400

    try:
        existing = db.get_conversation(conversation_id)
        if existing is None:
            return jsonify({"success": False, "message": "会话记录不存在"}), 404

        db.update_conversation(conversation_id, updates)
        return jsonify({"success": True, "message": "会话记录更新成功"}), 200
    except Exception as exc:
        logger.error("更新会话记录失败: %s", exc)
        return jsonify({"success": False, "message": "更新失败，请稍后重试"}), 500


@api.route("/conversation/<int:conversation_id>", methods=["DELETE"])
@auth_required
@log_action("删除会话记录")
def delete_conversation(conversation_id):
    """删除一条会话记录。"""
    try:
        existing = db.get_conversation(conversation_id)
        if existing is None:
            return jsonify({"success": False, "message": "会话记录不存在"}), 404

        db.delete_conversation(conversation_id)
        return jsonify({"success": True, "message": "会话记录已删除"}), 200
    except Exception as exc:
        logger.error("删除会话记录失败: %s", exc)
        return jsonify({"success": False, "message": "删除失败，请稍后重试"}), 500


@api.route("/conversation/batch-organize", methods=["POST"])
@auth_required
@log_action("批量整理会话")
def batch_organize():
    """批量将多条原始会话整理为结构化记录。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供待整理的会话列表"}), 400

    conversations = data.get("conversations") or data.get("items")
    if not conversations or not isinstance(conversations, list):
        return jsonify({"success": False, "message": "会话列表不能为空"}), 400

    if len(conversations) > 50:
        return jsonify({"success": False, "message": "单次批量操作最多处理 50 条记录"}), 400

    results = []
    errors = []

    for idx, item in enumerate(conversations):
        raw_content = item.get("content") or item.get("raw_content")
        if not raw_content:
            errors.append({"index": idx, "message": "会话内容为空"})
            continue
        try:
            structured = conversation_engine.organize(
                raw_content=raw_content,
                student_name=item.get("student_name"),
                context=item.get("context"),
            )
            results.append({"index": idx, "data": structured, "status": "success"})
        except Exception as exc:
            errors.append({"index": idx, "message": "内部错误，请稍后重试"})

    return jsonify({
        "success": True,
        "message": "批量整理完成：成功 {} 条，失败 {} 条".format(len(results), len(errors)),
        "data": {
            "results": results,
            "errors": errors,
        },
    }), 200

# ===================================================================
# 3. 情绪分析路由 (Emotion Routes)
# ===================================================================

@api.route("/emotion/analyze", methods=["POST"])
@auth_required
@log_action("情绪分析")
def analyze_emotion():
    """上传音频文件并返回情绪分析结果。"""
    if "audio_file" not in request.files:
        return jsonify({"success": False, "message": "请上传音频文件"}), 400

    audio_file = request.files["audio_file"]
    if not audio_file.filename:
        return jsonify({"success": False, "message": "文件名不能为空"}), 400

    allowed_extensions = {".wav", ".mp3", ".m4a", ".ogg", ".flac"}
    ext = os.path.splitext(audio_file.filename)[1].lower()
    if ext not in allowed_extensions:
        return jsonify({
            "success": False,
            "message": "不支持的音频格式 '{}'，允许的格式：{}".format(
                ext, ", ".join(allowed_extensions)
            ),
        }), 400

    if emotion_analyzer is None:
        return jsonify({"success": False, "message": "情绪分析引擎未初始化，请检查模型配置"}), 503

    try:
        # Save uploaded file to a temp path for the engine
        suffix = os.path.splitext(audio_file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        try:
            result = emotion_analyzer.analyze_single(tmp_path)
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass

        student_name = (request.form.get("student_name") or "").strip() or "未知学生"
        student_class = (request.form.get("student_class") or "").strip()
        analyzer_id = g.user_id if getattr(g, "user_type", "staff") != "student" else None

        try:
            intensity = int(float(result.get("intensity"))) if result.get("intensity") is not None else None
        except (TypeError, ValueError):
            intensity = None

        db.create_emotion_log(
            student_name=student_name,
            student_class=student_class,
            emotion=result.get("emotion", "正常"),
            confidence=result.get("confidence"),
            intensity=intensity,
            audio_path=audio_file.filename,
            risk_level=result.get("risk_level", "low"),
            analyzed_by=analyzer_id,
        )

        risk_level = result.get("risk_level", "low")
        if risk_level in ("high", "critical"):
            db.create_alert(
                student_name=student_name,
                student_class=student_class,
                risk_level="high",
                emotion_type=result.get("emotion"),
                intensity=intensity,
                description="语音情绪分析识别到高风险：{}，强度 {}/10".format(
                    result.get("emotion"), result.get("intensity")
                ),
                assigned_to=analyzer_id,
            )

        result["student_name"] = student_name
        result["student_class"] = student_class

        return jsonify({
            "success": True,
            "message": "情绪分析完成",
            "data": result,
        }), 200
    except Exception as exc:
        logger.error("情绪分析失败: %s", exc)
        return jsonify({"success": False, "message": "情绪分析失败: " + "内部错误，请稍后重试"}), 500


@api.route("/emotion/batch-analyze", methods=["POST"])
@auth_required
@log_action("批量情绪分析")
def batch_analyze_emotion():
    """批量分析目录中的音频文件。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供音频文件路径或 ID 列表"}), 400

    audio_paths = data.get("audio_paths") or data.get("file_ids")
    if not audio_paths or not isinstance(audio_paths, list):
        return jsonify({"success": False, "message": "请提供有效的文件列表"}), 400

    if len(audio_paths) > 100:
        return jsonify({"success": False, "message": "单次批量操作最多处理 100 个文件"}), 400

    try:
        result = emotion_analyzer.batch_analyze(audio_paths)
        return jsonify({
            "success": True,
            "message": "批量分析完成，共处理 {} 个文件".format(len(audio_paths)),
            "data": result,
        }), 200
    except Exception as exc:
        logger.error("批量情绪分析失败: %s", exc)
        return jsonify({"success": False, "message": "批量分析失败: " + "内部错误，请稍后重试"}), 500


@api.route("/emotion/logs", methods=["GET"])
@auth_required
@log_action("查看情绪日志")
def list_emotion_logs():
    """分页获取情绪分析日志，支持过滤。"""
    try:
        filters = {
            "student_name": request.args.get("student_name"),
            "risk_level": request.args.get("risk_level"),
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

        cid = g.user_id if getattr(g, "role", "") == "counselor" else None
        result = db.get_emotion_logs(
            filters=filters,
            page=page,
            per_page=per_page,
            counselor_id=cid,
        )

        return jsonify({
            "success": True,
            "data": result.get("items", []),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": result.get("total", 0),
                "total_pages": result.get("total_pages", 0),
            },
        }), 200
    except Exception as exc:
        logger.error("获取情绪日志失败: %s", exc)
        return jsonify({"success": False, "message": "获取情绪日志失败"}), 500




REALTIME_REVIEW_RULES = [
    {"min": 9, "max": 10, "risk_level": "high", "days": 1, "priority": "high", "label": "\u9ad8\u5371", "action": "24\u5c0f\u65f6\u5185\u590d\u67e5\uff0c\u5fc5\u8981\u65f6\u540c\u6b65\u5b66\u5de5\u4e0e\u5fc3\u7406\u4e2d\u5fc3\u3002"},
    {"min": 7, "max": 8, "risk_level": "high", "days": 3, "priority": "high", "label": "\u9ad8\u98ce\u9669", "action": "3\u65e5\u5185\u590d\u67e5\uff0c\u786e\u8ba4\u7761\u7720\u3001\u996e\u98df\u3001\u5b66\u4e60\u538b\u529b\u548c\u652f\u6301\u7cfb\u7edf\u3002"},
    {"min": 5, "max": 6, "risk_level": "medium", "days": 7, "priority": "medium", "label": "\u4e2d\u98ce\u9669", "action": "7\u65e5\u5185\u590d\u67e5\uff0c\u6301\u7eed\u89c2\u5bdf\u60c5\u7eea\u6ce2\u52a8\u4e0e\u884c\u4e3a\u53d8\u5316\u3002"},
    {"min": 3, "max": 4, "risk_level": "low", "days": 14, "priority": "low", "label": "\u8f7b\u5ea6\u5173\u6ce8", "action": "14\u65e5\u5185\u56de\u8bbf\uff0c\u63d0\u4f9b\u81ea\u52a9\u8c03\u9002\u5efa\u8bae\u3002"},
    {"min": 1, "max": 2, "risk_level": "low", "days": 30, "priority": "low", "label": "\u5e38\u89c4\u5173\u6ce8", "action": "30\u65e5\u5185\u5e38\u89c4\u5173\u6000\u56de\u8bbf\u3002"},
]


def _realtime_followup_rule(intensity):
    """Return review interval rule by 1-10 emotion intensity."""
    try:
        score = int(intensity or 1)
    except (TypeError, ValueError):
        score = 1
    score = max(1, min(10, score))
    for rule in REALTIME_REVIEW_RULES:
        if rule["min"] <= score <= rule["max"]:
            return dict(rule)
    return dict(REALTIME_REVIEW_RULES[-1])


def _realtime_number(value, default=0.0):
    try:
        if value in (None, "", "--"):
            return default
        number = float(value)
    except (TypeError, ValueError):
        return default
    return number


def _realtime_percent_value(item, *keys):
    for key in keys:
        if key in item and item.get(key) not in (None, "", "--"):
            value = _realtime_number(item.get(key), 0.0)
            return max(0.0, min(100.0, value * 100 if 0 < value <= 1 else value))
    return 0.0


def _avg_metric(cleaned, key):
    values = [_realtime_number(item.get(key), 0.0) for item in cleaned]
    return round(sum(values) / len(values), 1) if values else 0.0


def _peak_metric(cleaned, key):
    values = [_realtime_number(item.get(key), 0.0) for item in cleaned]
    return round(max(values), 1) if values else 0.0


def _weighted_signal_score(averages, peaks):
    weights = {
        "brow_furrow": 0.24,
        "gaze_instability": 0.14,
        "head_down": 0.11,
        "slouch": 0.11,
        "posture_stiffness": 0.10,
        "forward_head": 0.08,
        "touch_nose": 0.06,
        "scratch_head": 0.06,
        "hand_near_face": 0.04,
        "pause_ratio": 0.04,
        "speech_rate": 0.02,
    }
    total = 0.0
    for key, weight in weights.items():
        avg_value = averages.get(key, 0.0)
        peak_value = peaks.get(key, 0.0)
        signal_value = avg_value * 0.60 + peak_value * 0.40
        if key == "brow_furrow" and peak_value >= 45:
            signal_value = min(100.0, signal_value * 1.18)
        total += signal_value * weight
    return max(0.0, min(100.0, total))


REALTIME_SIGNAL_LABELS = {
    "brow_furrow": "\u76b1\u7709",
    "gaze_instability": "\u773c\u795e\u98d8\u5ffd",
    "head_down": "\u4f4e\u5934",
    "slouch": "\u5f2f\u8170/\u9a7c\u80cc",
    "posture_stiffness": "\u5750\u59ff\u50f5\u786c",
    "forward_head": "\u8eab\u4f53\u524d\u503e",
    "shoulder_slope": "\u80a9\u7ebf\u503e\u659c",
    "touch_nose": "\u6478\u9f3b\u5b50",
    "scratch_head": "\u6320\u5934",
    "hand_near_face": "\u624b\u90e8\u9760\u8fd1\u9762\u90e8",
    "pause_ratio": "\u60c5\u7eea\u6027\u505c\u987f",
    "speech_rate": "\u8bed\u901f\u5f02\u5e38",
    "audio_volume": "\u97f3\u91cf\u6ce2\u52a8",
}


def _emotion_risk_bonus(emotion):
    if emotion in ("\u7126\u8651", "\u538b\u6291", "\u6050\u60e7", "\u6124\u6012", "\u60b2\u4f24"):
        return 1.2
    if emotion in ("\u4f4e\u843d", "\u7d27\u5f20", "\u70e6\u8e81", "\u538c\u6076"):
        return 0.8
    return 0.0


def _summarize_realtime_signals(review_detail):
    peak_metrics = (review_detail or {}).get("peak_metrics") or {}
    signals = []
    for key, value in peak_metrics.items():
        label = REALTIME_SIGNAL_LABELS.get(key)
        if not label:
            continue
        numeric = _realtime_number(value, 0.0)
        if numeric >= 25:
            signals.append((numeric, "{}{}%".format(label, int(round(numeric)))))
    signals.sort(reverse=True)
    if not signals:
        return "\u6682\u672a\u6355\u6349\u5230\u660e\u663e\u9ad8\u5f3a\u5ea6\u5fae\u52a8\u4f5c"
    return "\u3001".join(item[1] for item in signals[:5])


def _calculate_realtime_review_score(cleaned, peak_emotion, peak_intensity, avg_intensity):
    metric_keys = [
        "brow_furrow", "gaze_instability", "head_down", "slouch", "posture_stiffness",
        "forward_head", "shoulder_slope", "touch_nose", "scratch_head", "hand_near_face",
        "pause_ratio", "speech_rate", "audio_volume",
    ]
    averages = {key: _avg_metric(cleaned, key) for key in metric_keys}
    peaks = {key: _peak_metric(cleaned, key) for key in metric_keys}
    action_match_confidence = _weighted_signal_score(averages, peaks)
    visual_score = action_match_confidence / 10.0
    brow_peak = peaks.get("brow_furrow", 0.0)
    brow_bonus = 0.6 if brow_peak >= 65 else 0.35 if brow_peak >= 45 else 0.0
    emotion_score = peak_intensity * 0.48 + avg_intensity * 0.24 + _emotion_risk_bonus(peak_emotion)
    multimodal_score = visual_score * 0.32 + brow_bonus
    score = round(max(1.0, min(10.0, emotion_score + multimodal_score)))
    return int(score), {
        "score": int(score),
        "visual_signal_score": round(visual_score, 1),
        "action_match_confidence": round(action_match_confidence, 1),
        "brow_bonus": brow_bonus,
        "avg_metrics": averages,
        "peak_metrics": peaks,
        "basis": {
            "peak_intensity": peak_intensity,
            "avg_intensity": avg_intensity,
            "emotion_bonus": _emotion_risk_bonus(peak_emotion),
            "visual_weight": 0.32,
            "brow_weight": 0.24,
        },
    }


def _normalize_realtime_risk(risk_level, intensity):
    rule = _realtime_followup_rule(intensity)
    if risk_level in ("critical", "high", "medium", "low"):
        if risk_level == "critical":
            rule["risk_level"] = "high"
            rule["days"] = 1
            rule["priority"] = "high"
            rule["label"] = "\u9ad8\u5371"
        else:
            rule["risk_level"] = risk_level
    return rule


def _format_realtime_rule_text():
    return "\uff1b".join(
        "{}-{}\u5206\uff1a{}\u65e5\u540e\u590d\u67e5".format(item["min"], item["max"], item["days"])
        for item in REALTIME_REVIEW_RULES
    )


@api.route("/emotion/realtime-log", methods=["POST"])
@role_required(["counselor", "super_admin", "student_affairs"])
@log_action("\u8bb0\u5f55\u5b9e\u65f6\u60c5\u7eea\u5206\u6790")
def create_realtime_emotion_log():
    """\u4fdd\u5b58\u8001\u5e08\u7aef\u89c6\u9891\u901a\u8bdd\u4e2d\u7684\u5b9e\u65f6\u60c5\u7eea\u5206\u6790\u6458\u8981\uff0c\u4f9b\u7ba1\u7406\u5458\u7aef\u770b\u677f\u7559\u75d5\u3002"""
    try:
        data = request.get_json(silent=True) or {}
        student_name = (data.get("student_name") or "\u672a\u77e5\u5b66\u751f").strip()
        student_class = (data.get("student_class") or data.get("class_name") or "\u5b9e\u65f6\u89c6\u9891\u901a\u8bdd").strip()
        emotion = (data.get("emotion") or "\u6b63\u5e38").strip()
        confidence = data.get("confidence")
        if confidence is not None:
            confidence = float(confidence)
            if confidence > 1:
                confidence = confidence / 100.0
            confidence = max(0.0, min(1.0, confidence))
        intensity = int(data.get("intensity") or 1)
        intensity = max(1, min(10, intensity))
        risk_level = data.get("risk_level")
        if not risk_level:
            risk_level = "high" if intensity >= 7 else "medium" if intensity >= 5 else "low"
        analyzer_id = g.user_id if getattr(g, "user_type", "staff") != "student" else None
        log_id = db.create_emotion_log(
            student_name=student_name,
            student_class=student_class,
            emotion=emotion,
            confidence=confidence,
            intensity=intensity,
            audio_path="\u5b9e\u65f6\u89c6\u9891\u901a\u8bdd",
            risk_level=risk_level,
            analyzed_by=analyzer_id,
        )
        if risk_level in ("high", "medium"):
            db.create_alert(
                student_name=student_name,
                student_class=student_class,
                risk_level=risk_level,
                emotion_type=emotion,
                intensity=intensity,
                description="\u89c6\u9891\u901a\u8bdd\u5b9e\u65f6\u60c5\u7eea\u8bc6\u522b\u81ea\u52a8\u8bb0\u5f55\uff1a{}\uff0c\u5f3a\u5ea6 {}/10\uff0c\u7f6e\u4fe1\u5ea6 {}%".format(
                    emotion, intensity, int((confidence or 0) * 100)
                ),
                assigned_to=analyzer_id,
            )
        return jsonify({"success": True, "data": {"id": log_id}}), 200
    except Exception as exc:
        logger.error("\u4fdd\u5b58\u5b9e\u65f6\u60c5\u7eea\u65e5\u5fd7\u5931\u8d25: %s", exc)
        return jsonify({"success": False, "message": "\u4fdd\u5b58\u5b9e\u65f6\u60c5\u7eea\u65e5\u5fd7\u5931\u8d25"}), 500


@api.route("/emotion/realtime-call-summary", methods=["POST"])
@role_required(["counselor", "super_admin", "student_affairs"])
@log_action("\u751f\u6210\u89c6\u9891\u901a\u8bdd\u60c5\u7eea\u603b\u7ed3")
def create_realtime_emotion_summary():
    """Create a unified summary after a video call and schedule review."""
    try:
        data = request.get_json(silent=True) or {}
        student_pk = data.get("student_pk") or data.get("student_db_id") or data.get("student_id")
        student_id_str = data.get("student_id_str") or data.get("student_no")
        student_name = (data.get("student_name") or "\u672a\u77e5\u5b66\u751f").strip()
        student_class = (data.get("student_class") or data.get("class_name") or "\u5b9e\u65f6\u89c6\u9891\u901a\u8bdd").strip()
        samples = data.get("samples") or []
        call_started_at = data.get("call_started_at") or ""
        call_ended_at = data.get("call_ended_at") or ""
        duration_seconds = int(data.get("duration_seconds") or 0)

        cleaned = []
        for item in samples:
            if not isinstance(item, dict):
                continue
            emotion = (item.get("emotion") or item.get("text") or "\u6b63\u5e38").strip()
            try:
                intensity = int(item.get("intensity") or 1)
            except (TypeError, ValueError):
                intensity = 1
            intensity = max(1, min(10, intensity))
            confidence = item.get("confidence")
            try:
                confidence = float(confidence) if confidence is not None and confidence != "--" else 0
            except (TypeError, ValueError):
                confidence = 0
            if confidence > 1:
                confidence = confidence / 100.0
            cleaned.append({
                "emotion": emotion,
                "intensity": intensity,
                "confidence": max(0.0, min(1.0, confidence)),
                "risk_level": item.get("risk_level") or item.get("riskLevel") or "",
                "audio_volume": _realtime_percent_value(item, "audioVolume", "audio_volume"),
                "speech_rate": _realtime_percent_value(item, "speechRate", "speech_rate"),
                "pause_ratio": _realtime_percent_value(item, "pauseRatio", "pause_ratio"),
                "brow_furrow": _realtime_percent_value(item, "browFurrow", "brow_furrow"),
                "head_down": _realtime_percent_value(item, "headDownPercent", "head_down"),
                "posture_stiffness": _realtime_percent_value(item, "postureStiffness", "posture_stiffness"),
                "forward_head": _realtime_percent_value(item, "forwardHead", "forward_head"),
                "shoulder_slope": _realtime_percent_value(item, "shoulderSlope", "shoulder_slope"),
                "slouch": _realtime_percent_value(item, "slouch", "bendOver", "bend_over"),
                "scratch_head": _realtime_percent_value(item, "scratchHead", "scratch_head"),
                "touch_nose": _realtime_percent_value(item, "touchNose", "touch_nose"),
                "hand_near_face": _realtime_percent_value(item, "handNearFace", "hand_near_face"),
                "gaze_instability": _realtime_percent_value(item, "gazeInstability", "gaze_instability"),
            })

        if not cleaned:
            emotion = (data.get("emotion") or "\u6b63\u5e38").strip()
            intensity = int(data.get("intensity") or 1)
            cleaned.append({"emotion": emotion, "intensity": max(1, min(10, intensity)), "confidence": 0, "risk_level": data.get("risk_level") or "low", "brow_furrow": 0, "head_down": 0, "posture_stiffness": 0, "forward_head": 0, "shoulder_slope": 0, "slouch": 0, "scratch_head": 0, "touch_nose": 0, "hand_near_face": 0, "gaze_instability": 0, "speech_rate": 0, "pause_ratio": 0, "audio_volume": 0})

        emotion_counts = {}
        max_sample = cleaned[0]
        intensity_sum = 0
        confidence_sum = 0
        for item in cleaned:
            emotion_counts[item["emotion"]] = emotion_counts.get(item["emotion"], 0) + 1
            intensity_sum += item["intensity"]
            confidence_sum += item.get("confidence") or 0
            if (item["intensity"], item.get("confidence") or 0) > (max_sample["intensity"], max_sample.get("confidence") or 0):
                max_sample = item
        dominant_emotion = sorted(emotion_counts.items(), key=lambda x: x[1], reverse=True)[0][0]
        peak_emotion = max_sample["emotion"]
        peak_intensity = max_sample["intensity"]
        avg_intensity = round(intensity_sum / len(cleaned), 1)
        avg_confidence = round(confidence_sum / len(cleaned), 2)
        review_score, review_detail = _calculate_realtime_review_score(cleaned, peak_emotion, peak_intensity, avg_intensity)
        rule = _normalize_realtime_risk(None, review_score)
        risk_level = rule["risk_level"]
        follow_up_date = datetime.now() + timedelta(days=rule["days"])
        signal_text = _summarize_realtime_signals(review_detail)
        analyzer_id = g.user_id if getattr(g, "user_type", "staff") != "student" else None

        student = db.find_student_for_realtime_summary(
            student_pk=student_pk,
            student_id_str=student_id_str,
            student_name=student_name,
        )
        if student:
            student_name = student.get("name") or student_name
            student_class = student.get("class_name") or student.get("college") or student_class
            student_id_str = student.get("student_id") or student_id_str

        summary = (
            "\u89c6\u9891\u901a\u8bdd\u5b9e\u65f6\u60c5\u7eea\u603b\u7ed3\uff1a\u672c\u6b21\u5171\u91c7\u96c6 {} \u6761\u6709\u6548\u5206\u6790\u70b9\uff0c\u4e3b\u5bfc\u60c5\u7eea\u4e3a{}\uff0c\u5cf0\u503c\u60c5\u7eea\u4e3a{}\uff0c"
            "\u6700\u9ad8\u5f3a\u5ea6 {}/10\uff0c\u5e73\u5747\u5f3a\u5ea6 {}/10\uff0c\u5fae\u52a8\u4f5c\u590d\u67e5\u7efc\u5408\u5206 {}/10\uff0c\u5e73\u5747\u7f6e\u4fe1\u5ea6 {}%\u3002\u5173\u952e\u5fae\u52a8\u4f5c\uff1a{}\u3002\u5efa\u8bae\uff1a{}"
        ).format(len(cleaned), dominant_emotion, peak_emotion, peak_intensity, avg_intensity, review_score, int(avg_confidence * 100), signal_text, rule["action"])
        structured = json.dumps({
            "call_started_at": call_started_at,
            "call_ended_at": call_ended_at,
            "duration_seconds": duration_seconds,
            "dominant_emotion": dominant_emotion,
            "peak_emotion": peak_emotion,
            "peak_intensity": peak_intensity,
            "avg_intensity": avg_intensity,
            "avg_confidence": avg_confidence,
            "risk_level": risk_level,
            "review_score": review_score,
            "review_detail": review_detail,
            "key_signals": signal_text,
            "review_rule": rule,
            "review_rule_text": _format_realtime_rule_text(),
            "emotion_distribution": emotion_counts,
            "samples_count": len(cleaned),
        }, ensure_ascii=False)

        log_id = db.create_emotion_log(
            student_name=student_name,
            student_class=student_class,
            emotion=peak_emotion,
            confidence=avg_confidence,
            intensity=review_score,
            audio_path="\u89c6\u9891\u901a\u8bdd\u7ed3\u675f\u603b\u7ed3",
            risk_level=risk_level,
            analyzed_by=analyzer_id,
        )

        profile_id = None
        emotion_tracking_id = None
        reminder_id = None
        if student:
            sid = student.get("id")
            profile_id = db.create_student_profile(
                student_id=sid,
                counselor_id=analyzer_id,
                record_type="video_emotion_summary",
                summary=summary,
                structured_content=structured,
                emotion_tags={
                    "dominant": dominant_emotion,
                    "peak": peak_emotion,
                    "distribution": emotion_counts,
                    "review_score": review_score,
                    "key_signals": signal_text,
                    "samples_count": len(cleaned),
                },
                risk_level=risk_level,
                counselor_impression="\u7cfb\u7edf\u81ea\u52a8\u751f\u6210\uff0c\u5efa\u8bae\u8001\u5e08\u7ed3\u5408\u8c08\u8bdd\u5185\u5bb9\u590d\u6838\u3002",
                follow_up_needed=True,
                follow_up_date=follow_up_date,
                audio_path="\u5b9e\u65f6\u89c6\u9891\u901a\u8bdd",
            )
            emotion_tracking_id = db.create_emotion_tracking(
                student_id=sid,
                emotion=peak_emotion,
                intensity=review_score,
                risk_level=risk_level,
                source="video_call_summary",
                notes=summary,
                recorded_by=analyzer_id,
                auto_reminder=False,
            )
            db.update_student_risk_state(sid, risk_level, peak_emotion)
            reminder_id = db.create_realtime_followup_reminder(
                student_id=sid,
                counselor_id=analyzer_id,
                title="\u3010{}\u3011{} \u89c6\u9891\u901a\u8bdd\u540e\u60c5\u7eea\u590d\u67e5".format(rule["label"], student_name),
                description=summary + " \u590d\u67e5\u89c4\u5219\uff1a" + _format_realtime_rule_text(),
                priority=rule["priority"],
                due_date=follow_up_date,
            )

        if risk_level in ("high", "critical"):
            db.create_alert(
                student_name=student_name,
                student_class=student_class,
                risk_level="high",
                emotion_type=peak_emotion,
                intensity=review_score,
                description=summary + " \u5efa\u8bae\u590d\u67e5\u65f6\u95f4\uff1a{}\u3002".format(follow_up_date.strftime("%Y-%m-%d")),
                assigned_to=analyzer_id,
            )

        return jsonify({
            "success": True,
            "message": "\u89c6\u9891\u901a\u8bdd\u60c5\u7eea\u603b\u7ed3\u5df2\u751f\u6210",
            "data": {
                "log_id": log_id,
                "profile_id": profile_id,
                "emotion_tracking_id": emotion_tracking_id,
                "reminder_id": reminder_id,
                "student_name": student_name,
                "student_id": student_id_str,
                "student_class": student_class,
                "summary": summary,
                "dominant_emotion": dominant_emotion,
                "peak_emotion": peak_emotion,
                "peak_intensity": peak_intensity,
                "avg_intensity": avg_intensity,
                "review_score": review_score,
                "review_detail": review_detail,
                "key_signals": signal_text,
                "avg_confidence": avg_confidence,
                "risk_level": risk_level,
                "risk_label": rule["label"],
                "follow_up_days": rule["days"],
                "follow_up_date": follow_up_date.strftime("%Y-%m-%d"),
                "follow_up_action": rule["action"],
                "review_rule_text": _format_realtime_rule_text(),
                "samples_count": len(cleaned),
                "emotion_distribution": emotion_counts,
            }
        }), 200
    except Exception as exc:
        logger.error("create realtime emotion summary failed: %s", exc)
        return jsonify({"success": False, "message": "\u751f\u6210\u89c6\u9891\u901a\u8bdd\u60c5\u7eea\u603b\u7ed3\u5931\u8d25"}), 500


@api.route("/emotion/seed-demo", methods=["POST"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("生成实时情绪演示数据")
def seed_realtime_demo_logs():
    """提前写入一批实时分析演示数据，方便比赛现场展示管理员可视化。"""
    try:
        samples = [
            ("宋美琳", "计算机科学与技术1班", "焦虑", 0.86, 8, "high"),
            ("梁雨霏", "计算机科学与技术2班", "紧张", 0.78, 6, "medium"),
            ("袁伟杰", "机械工程1班", "低落", 0.74, 6, "medium"),
            ("萧睿", "机械工程2班", "平静", 0.69, 3, "low"),
            ("徐雅馨", "外国语言文学1班", "压抑", 0.82, 8, "high"),
            ("周睿阳", "外国语言文学2班", "正常", 0.72, 2, "low"),
            ("陈诗涵", "经济管理1班", "烦躁", 0.77, 5, "medium"),
            ("高铭远", "电子信息1班", "焦虑", 0.81, 7, "high"),
            ("杨思源", "电子信息2班", "平静", 0.68, 3, "low"),
            ("郑思颖", "汉语言文学1班", "低落", 0.73, 6, "medium"),
            ("马晓婷", "艺术设计1班", "紧张", 0.76, 6, "medium"),
            ("胡天宇", "计算机科学与技术1班", "正常", 0.71, 2, "low"),
        ]
        demo_source = "\u6bd4\u8d5b\u6f14\u793a\u5b9e\u65f6\u89c6\u9891\u901a\u8bdd"
        existing = db.get_emotion_logs(page=1, per_page=10000).get("items", [])
        existing_demo_count = sum(1 for item in existing if item.get("audio_path") == demo_source)
        if existing_demo_count >= len(samples):
            return jsonify({
                "success": True,
                "message": "\u6f14\u793a\u6570\u636e\u5df2\u5b58\u5728\uff0c\u65e0\u9700\u91cd\u590d\u751f\u6210",
                "count": existing_demo_count,
            }), 200

        analyzer_id = g.user_id if getattr(g, "user_type", "staff") != "student" else None
        created = 0
        for student_name, student_class, emotion, confidence, intensity, risk_level in samples:
            db.create_emotion_log(
                student_name=student_name,
                student_class=student_class,
                emotion=emotion,
                confidence=confidence,
                intensity=intensity,
                audio_path=demo_source,
                risk_level=risk_level,
                analyzed_by=analyzer_id,
            )
            if risk_level in ("high", "medium"):
                db.create_alert(
                    student_name=student_name,
                    student_class=student_class,
                    risk_level=risk_level,
                    emotion_type=emotion,
                    intensity=intensity,
                    description="演示数据：实时视频通话识别到{}，建议持续关注。".format(emotion),
                    assigned_to=analyzer_id,
                )
            created += 1
        return jsonify({"success": True, "message": "已生成 {} 条演示数据".format(created), "count": created}), 200
    except Exception as exc:
        logger.error("生成实时情绪演示数据失败: %s", exc)
        return jsonify({"success": False, "message": "生成演示数据失败"}), 500
@api.route("/emotion/statistics", methods=["GET"])
@auth_required
@log_action("查看情绪统计")
def emotion_statistics():
    """获取情绪统计数据。"""
    try:
        params = {
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
            "college": request.args.get("college"),
            "class_name": request.args.get("class_name"),
        }
        # 辅导员只看自己管辖学生的情绪数据 — 从 token 直接解析 role
        cid = None
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            try:
                payload = auth.verify_token(auth_header[7:])
                if payload and isinstance(payload, dict) and payload.get("role") == "counselor":
                    cid = payload.get("user_id")
            except Exception:
                pass
        params = {k: v for k, v in params.items() if v is not None}
        stats = db.get_emotion_statistics(counselor_id=cid, **params)
        return jsonify({"success": True, "data": stats}), 200
    except Exception as exc:
        logger.error("获取情绪统计失败: %s", exc)
        return jsonify({"success": False, "message": "获取统计数据失败"}), 500


@api.route("/emotion/trends", methods=["GET"])
@auth_required
@log_action("查看情绪趋势")
def emotion_trends():
    """获取情绪趋势数据，用于折线图展示。"""
    try:
        days = min(365, max(1, request.args.get("days", 30, type=int)))
        student_id = request.args.get("student_id")
        class_name = request.args.get("class_name")

        trends = db.get_emotion_trends(
            days=days,
            student_id=student_id,
            class_name=class_name,
        )
        return jsonify({"success": True, "data": trends}), 200
    except Exception as exc:
        logger.error("获取情绪趋势失败: %s", exc)
        return jsonify({"success": False, "message": "获取趋势数据失败"}), 500


@api.route("/emotion/heatmap", methods=["GET"])
@auth_required
@log_action("查看情绪热力图")
def emotion_heatmap():
    """获取情绪热力图数据。"""
    try:
        date_from = request.args.get("date_from")
        date_to = request.args.get("date_to")
        college = request.args.get("college")

        heatmap = db.get_emotion_heatmap(
            date_from=date_from,
            date_to=date_to,
            college=college,
        )
        return jsonify({"success": True, "data": heatmap}), 200
    except Exception as exc:
        logger.error("获取热力图数据失败: %s", exc)
        return jsonify({"success": False, "message": "获取热力图数据失败"}), 500


@api.route("/network/emotion-graph", methods=["GET"])
@auth_required
@log_action("查看情绪网络图")
def emotion_network_graph():
    """获取情绪网络图数据：中心 → 情绪分支 → 学生节点（按严重程度着色）。"""
    try:
        role = getattr(g, "role", None)
        cid = g.user_id if role == "counselor" else None
        data = db.get_emotion_network(counselor_id=cid, role=role)
        return jsonify({"success": True, "data": data}), 200
    except Exception as exc:
        logger.error("获取情绪网络图失败: %s", exc)
        return jsonify({"success": False, "message": "获取网络图数据失败"}), 500


@api.route("/system/test-accounts", methods=["GET"])
def test_accounts():
    """动态下发测试账号列表（辅导员 + 学生），供登录页渲染，避免硬编码错位。"""
    try:
        accounts = db.get_test_accounts()
        return jsonify({"success": True, "data": accounts}), 200
    except Exception as exc:
        logger.error("获取测试账号失败: %s", exc)
        return jsonify({"success": False, "message": "获取测试账号失败"}), 500

# ===================================================================
# 4. 预警管理路由 (Alert Routes)
# ===================================================================

@api.route("/alert/list", methods=["GET"])
@auth_required
@log_action("查看预警列表")
def list_alerts():
    """分页获取风险预警列表。"""
    try:
        filters = {
            "risk_level": request.args.get("risk_level"),
            "status": request.args.get("status"),
            "college": request.args.get("college"),
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

        result = db.search_alerts(
            filters=filters,
            page=page,
            per_page=per_page,
        )

        return jsonify({
            "success": True,
            "data": result.get("items", []),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": result.get("total", 0),
                "total_pages": result.get("total_pages", 0),
            },
        }), 200
    except Exception as exc:
        logger.error("获取预警列表失败: %s", exc)
        return jsonify({"success": False, "message": "获取预警列表失败"}), 500


@api.route("/alert/<int:alert_id>/acknowledge", methods=["PUT"])
@auth_required
@log_action("确认预警")
def acknowledge_alert(alert_id):
    """将预警标记为已确认。"""
    try:
        existing = db.get_alert(alert_id)
        if existing is None:
            return jsonify({"success": False, "message": "预警记录不存在"}), 404

        if existing.get("status") == "acknowledged":
            return jsonify({"success": False, "message": "该预警已被确认"}), 400

        db.update_alert(alert_id, {
            "status": "acknowledged",
            "acknowledged_by": g.user_id,
            "acknowledged_at": datetime.utcnow().isoformat(),
        })
        return jsonify({"success": True, "message": "预警已确认"}), 200
    except Exception as exc:
        logger.error("确认预警失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/alert/<int:alert_id>/resolve", methods=["PUT"])
@auth_required
@log_action("解决预警")
def resolve_alert(alert_id):
    """将预警标记为已解决。"""
    data = request.get_json(silent=True) or {}

    try:
        existing = db.get_alert(alert_id)
        if existing is None:
            return jsonify({"success": False, "message": "预警记录不存在"}), 404

        updates = {
            "status": "resolved",
            "resolved_by": g.user_id,
            "resolved_at": datetime.utcnow().isoformat(),
        }
        resolution = data.get("resolution")
        if resolution:
            updates["resolution"] = resolution

        db.update_alert(alert_id, updates)
        return jsonify({"success": True, "message": "预警已解决"}), 200
    except Exception as exc:
        logger.error("解决预警失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/alert/statistics", methods=["GET"])
@auth_required
@log_action("查看预警统计")
def alert_statistics():
    """获取预警统计数据。"""
    try:
        params = {
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
            "college": request.args.get("college"),
        }
        params = {k: v for k, v in params.items() if v is not None}

        stats = db.get_alert_statistics(**params)
        return jsonify({"success": True, "data": stats}), 200
    except Exception as exc:
        logger.error("获取预警统计失败: %s", exc)
        return jsonify({"success": False, "message": "获取预警统计失败"}), 500

# ===================================================================
# 5. 知识库路由 (Knowledge Base Routes)
# ===================================================================

@api.route("/knowledge/upload", methods=["POST"])
@role_required(["super_admin", "student_affairs"])
@log_action("上传知识库文档")
def upload_knowledge():
    """上传文档到知识库。"""
    if "file" not in request.files:
        return jsonify({"success": False, "message": "请上传文件"}), 400

    file = request.files["file"]
    if not file.filename:
        return jsonify({"success": False, "message": "文件名不能为空"}), 400

    allowed_ext = {".txt", ".pdf", ".docx", ".doc", ".md"}
    ext = os.path.splitext(file.filename)[1].lower()
    if ext not in allowed_ext:
        return jsonify({
            "success": False,
            "message": "不支持的文件格式 '{}'，允许：{}".format(ext, ", ".join(allowed_ext)),
        }), 400

    try:
        # Save uploaded file to docs directory
        docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
        os.makedirs(docs_dir, exist_ok=True)
        save_path = os.path.join(docs_dir, file.filename)
        file.save(save_path)

        # Index the document
        result = knowledge_base.incremental_update(save_path)
        doc_id = result.get("doc_id", file.filename)

        return jsonify({
            "success": True,
            "message": "文档上传并索引成功",
            "data": {"document_id": doc_id, "filename": file.filename},
        }), 201
    except Exception as exc:
        logger.error("文档上传失败: %s", exc)
        return jsonify({"success": False, "message": "文档上传失败: " + "内部错误，请稍后重试"}), 500

@api.route("/knowledge/documents", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看知识库文档列表")
def list_documents():
    """列出已索引的知识库文档。"""
    try:
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))

        # Build document list from internal index
        seen = {}
        for item in knowledge_base._documents:
            did = item.get("doc_id", "unknown")
            if did not in seen:
                seen[did] = {"doc_id": did, "filename": did, "chunk_count": 0}
            seen[did]["chunk_count"] += 1
        docs = list(seen.values())
        total = len(docs)
        start = (page - 1) * per_page
        items = docs[start:start + per_page]
        return jsonify({"success": True, "data": items, "total": total}), 200
    except Exception as exc:
        logger.error("获取文档列表失败: %s", exc)
        return jsonify({"success": False, "message": "获取文档列表失败"}), 500


@api.route("/knowledge/documents/<string:document_id>", methods=["DELETE"])
@role_required(["super_admin"])
@log_action("删除知识库文档")
def delete_document(document_id):
    """从知识库中删除指定文档。"""
    try:
        success = knowledge_base.delete_document(document_id)
        if not success:
            return jsonify({"success": False, "message": "文档不存在"}), 404
        return jsonify({"success": True, "message": "文档已删除"}), 200
    except Exception as exc:
        logger.error("删除文档失败: %s", exc)
        return jsonify({"success": False, "message": "删除失败，请稍后重试"}), 500


@api.route("/knowledge/search", methods=["POST"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("搜索知识库")
def search_knowledge():
    """在知识库中检索相关内容。"""
    data = request.get_json(silent=True)
    if not data or not data.get("query"):
        return jsonify({"success": False, "message": "请输入搜索关键词"}), 400

    query = data["query"]
    top_k = min(20, max(1, data.get("top_k", 5)))

    try:
        if knowledge_base is not None:
            hits = knowledge_base.search(query, top_k=top_k)
            results = [
                {
                    "doc_id": hit.get("metadata", {}).get("source", "unknown"),
                    "score": round(hit.get("score", 0), 3),
                    "content": hit.get("content", ""),
                    "snippet": hit.get("content", "")[:300],
                    "source": hit.get("metadata", {}).get("source", "unknown"),
                }
                for hit in hits
            ]
            if not results:
                results = [{
                    "doc_id": "无匹配", "score": 0,
                    "content": "知识库中暂无与您搜索相关的内容",
                    "snippet": "请先上传相关文档到知识库", "source": "system",
                }]
        else:
            results = _fallback_knowledge_search(query, top_k)
        return jsonify({
            "success": True,
            "data": results,
            "query": query,
        }), 200
    except Exception as exc:
        logger.warning("RAG搜索失败，使用关键词后备: %s", exc)
        try:
            results = _fallback_knowledge_search(query, top_k)
            return jsonify({"success": True, "data": results, "query": query, "source": "keyword_fallback"}), 200
        except Exception as e2:
            return jsonify({"success": False, "message": "搜索失败，请稍后重试"}), 500


@api.route("/knowledge/stats", methods=["GET"])
@role_required(["super_admin", "student_affairs"])
@log_action("查看知识库统计")
def knowledge_stats():
    """获取知识库的统计数据。"""
    try:
        stats = knowledge_base.get_stats()
        return jsonify({"success": True, "data": stats}), 200
    except Exception as exc:
        logger.error("获取知识库统计失败: %s", exc)
        return jsonify({"success": False, "message": "获取统计信息失败"}), 500

# ===================================================================
# 6. 系统管理路由 (System Routes)
# ===================================================================

@api.route("/system/logs", methods=["GET"])
@role_required(["super_admin"])
@log_action("查看系统日志")
def system_logs():
    """分页获取系统操作日志。"""
    try:
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 50, type=int)))

        filters = {
            "user_id": request.args.get("user_id"),
            "action": request.args.get("action"),
            "date_from": request.args.get("date_from"),
            "date_to": request.args.get("date_to"),
        }
        filters = {k: v for k, v in filters.items() if v is not None}

        result = db.get_system_logs(filters=filters, page=page, per_page=per_page)

        return jsonify({
            "success": True,
            "data": result.get("items", []),
            "pagination": {
                "page": page,
                "per_page": per_page,
                "total": result.get("total", 0),
                "total_pages": result.get("total_pages", 0),
            },
        }), 200
    except Exception as exc:
        logger.error("获取系统日志失败: %s", exc)
        return jsonify({"success": False, "message": "获取系统日志失败"}), 500


@api.route("/system/dashboard", methods=["GET"])
@auth_required
@log_action("查看仪表盘")
def dashboard():
    """获取仪表盘综合数据：统计概览、情绪分布、风险分布、近期趋势"""
    try:
        from collections import Counter
        total_conversations = db.get_statistics().get("total_conversations", 0)
        total_emotions = db.get_statistics().get("total_emotion_logs", 0)
        stats = db.get_statistics()
        pending_alerts = stats.get("pending_alerts", 0)
        resolved_alerts = stats.get("resolved_alerts", 0)

        emotion_logs = db.get_emotion_logs(page=1, per_page=10000)
        emo_items = emotion_logs.get("items", [])
        emo_counts = Counter(item.get("emotion", "unknown") for item in emo_items)
        total_emo = len(emo_items) if emo_items else 1
        emotion_dist = {k: round(v / total_emo * 100) for k, v in emo_counts.most_common(6)}

        # ????
        alert_result_all = db.search_alerts(page=1, per_page=10000)
        all_alerts = alert_result_all.get("items", [])
        risk_counts = Counter(a.get("risk_level", "low") for a in all_alerts)
        risk_distribution = {
            "high": risk_counts.get("high", 0),
            "medium": risk_counts.get("medium", 0),
            "low": risk_counts.get("low", 0),
        }

        # ??7???
        from datetime import datetime as _dt, timedelta as _td
        today = _dt.now()
        trend_data = []
        for i in range(6, -1, -1):
            day = today - _td(days=i)
            day_str = day.strftime("%m-%d")
            day_emo = [e for e in emo_items
                       if e.get("created_at", "")[:10] == day.strftime("%Y-%m-%d")]
            trend_data.append({"date": day_str, "count": len(day_emo)})

        alert_result = db.search_alerts(page=1, per_page=5)
        recent_alerts = [
            {"id": a.get("id"), "student_name": a.get("student_name"), "emotion_type": a.get("emotion_type"),
             "intensity": a.get("intensity"), "risk_level": a.get("risk_level"), "status": a.get("status"),
             "created_at": a.get("created_at", "")}
            for a in alert_result.get("items", [])
        ]

        return jsonify({
            "conversations": total_conversations,
            "emotions": total_emotions,
            "alerts_pending": pending_alerts,
            "alerts_resolved": resolved_alerts,
            "knowledge_docs": 0,
            "emotion_distribution": emotion_dist,
            "risk_distribution": risk_distribution,
            "trend_data": trend_data,
            "recent_alerts": recent_alerts,
        }), 200
    except Exception as exc:
        logger.error("dashboard error: %s", exc)
        return jsonify({
            "conversations": 0, "emotions": 0, "alerts_pending": 0,
            "knowledge_docs": 0, "emotion_distribution": {},
            "risk_distribution": {}, "trend_data": [], "recent_alerts": [],
        }), 200

# ===================================================================
# 7. 学生管理路由 (Student Routes)
# ===================================================================

@api.route("/student/list", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看学生列表")
def list_students():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, request.args.get("per_page", 20, type=int))
    filters = {
        "search": request.args.get("search"),
        "class_name": request.args.get("class_name"),
        "risk_level": request.args.get("risk_level"),
    }
    filters = {k: v for k, v in filters.items() if v}
    # 辅导员只能看到自己管辖的学生
    counselor_id = g.user_id if g.role == "counselor" else None
    result = db.get_students(page=page, per_page=per_page, filters=filters, counselor_id=counselor_id)
    return jsonify({"success": True, "data": result["items"], "total": result["total"]}), 200


@api.route("/student/add", methods=["POST"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("添加学生")
def add_student():
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供学生信息"}), 400
    required = ["student_id", "name"]
    for field in required:
        if not data.get(field):
            return jsonify({"success": False, "message": f"缺少必填字段: {field}"}), 400
    try:
        sid = db.create_student(
            student_id=data["student_id"],
            name=data["name"],
            gender=data.get("gender", ""),
            college=data.get("college", ""),
            class_name=data.get("class_name", ""),
            phone=data.get("phone", ""),
            counselor_id=g.user_id,
            notes=data.get("notes", ""),
        )
        return jsonify({"success": True, "message": "学生添加成功", "data": {"id": sid}}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@api.route("/student/<int:sid>", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看学生详情")
def get_student(sid):
    with db.get_session() as session:
        from core.database import Student
        s = session.query(Student).get(sid)
        if not s:
            return jsonify({"success": False, "message": "学生不存在"}), 404
        return jsonify({"success": True, "data": db._to_dict(s)}), 200


@api.route("/student/<int:sid>", methods=["PUT"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("更新学生信息")
def update_student(sid):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供更新数据"}), 400
    allowed = {"name", "gender", "college", "class_name", "phone", "notes", "risk_level", "emotion_status"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"success": False, "message": "没有可更新的字段"}), 400
    ok = db.update_student(sid, updates)
    if ok:
        return jsonify({"success": True, "message": "更新成功"}), 200
    return jsonify({"success": False, "message": "学生不存在"}), 404


@api.route("/student/<int:sid>/profiles", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看学生档案")
def get_student_profiles(sid):
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, request.args.get("per_page", 20, type=int))
    result = db.get_student_profiles(sid, page=page, per_page=per_page)
    return jsonify({"success": True, "data": result["items"], "total": result["total"]}), 200


@api.route("/student/<int:sid>/profile/add", methods=["POST"])
@auth_required
@log_action("添加学生档案")
def add_student_profile(sid):
    data = request.get_json(silent=True)
    if not data or not data.get("summary"):
        return jsonify({"success": False, "message": "请提供谈话摘要"}), 400
    try:
        pid = db.create_student_profile(
            student_id=sid,
            counselor_id=g.user_id,
            record_type=data.get("record_type", "talk"),
            summary=data["summary"],
            structured_content=data.get("structured_content", ""),
            emotion_tags=data.get("emotion_tags"),
            risk_level=data.get("risk_level", "low"),
            counselor_impression=data.get("counselor_impression", ""),
            follow_up_needed=data.get("follow_up_needed", False),
            follow_up_date=data.get("follow_up_date"),
            audio_path=data.get("audio_path", ""),
        )
        return jsonify({"success": True, "message": "档案添加成功", "data": {"id": pid}}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@api.route("/student/<int:sid>/emotion", methods=["POST"])
@auth_required
@log_action("记录学生情绪")
def record_student_emotion(sid):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供情绪数据"}), 400
    try:
        eid = db.create_emotion_tracking(
            student_id=sid,
            emotion=data.get("emotion", "正常"),
            intensity=data.get("intensity", 5),
            risk_level=data.get("risk_level", "low"),
            source=data.get("source", "manual"),
            notes=data.get("notes", ""),
            recorded_by=g.user_id,
        )
        return jsonify({"success": True, "message": "情绪记录成功", "data": {"id": eid}}), 201
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500


@api.route("/student/<int:sid>/emotion/history", methods=["GET"])
@auth_required
@log_action("查看情绪历史")
def get_emotion_history(sid):
    days = min(365, request.args.get("days", 30, type=int))
    data = db.get_emotion_tracking(sid, days=days)
    return jsonify({"success": True, "data": data}), 200


@api.route("/student/reminder/list", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看提醒列表")
def list_reminders():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, request.args.get("per_page", 50, type=int))
    result = db.get_reminders(counselor_id=g.user_id, page=page, per_page=per_page)
    return jsonify({"success": True, "data": result["items"], "total": result["total"]}), 200


@api.route("/student/reminder/<int:rid>/complete", methods=["PUT"])
@auth_required
@log_action("完成提醒")
def complete_reminder_route(rid):
    ok = db.complete_reminder(rid)
    if ok:
        return jsonify({"success": True, "message": "提醒已完成"}), 200
    return jsonify({"success": False, "message": "提醒不存在"}), 404


@api.route("/student/stats", methods=["GET"])
@auth_required
@log_action("查看学生统计")
def student_stats():
    stats = db.get_student_stats()
    return jsonify({"success": True, "data": stats}), 200


@api.route("/student/calendar", methods=["GET"])
@auth_required
@log_action("查看日历事件")
def calendar_events():
    year = request.args.get("year", datetime.utcnow().year, type=int)
    month = request.args.get("month", datetime.utcnow().month, type=int)
    events = db.get_calendar_events(year, month)
    return jsonify({"success": True, "data": events}), 200

# ===================================================================
# 辅导员列表 API（供学生预约选择）
# ===================================================================

@api.route("/counselors/list", methods=["GET"])
@auth_required
def list_counselors():
    """获取所有辅导员列表（供学生预约选择）"""
    try:
        counselors = db.get_counselors()
        return jsonify({"success": True, "data": counselors}), 200
    except Exception as exc:
        logger.error("获取辅导员列表失败: %s", exc)
        return jsonify({"success": False, "message": "获取失败"}), 500

# ===================================================================
# 自定义待办 API
# ===================================================================

@api.route("/workplan/todo/add", methods=["POST"])
@auth_required
@log_action("添加待办")
def add_todo():
    """添加自定义待办事项"""
    data = request.get_json(silent=True)
    if not data or not data.get("title"):
        return jsonify({"success": False, "message": "请输入待办标题"}), 400

    try:
        tid = db.create_todo(
            user_id=g.user_id,
            title=data["title"],
            description=data.get("description", ""),
            category=data.get("category", "work_task"),
            priority=data.get("priority", "medium"),
            due_date=data.get("due_date"),
        )
        return jsonify({"success": True, "message": "待办已添加", "data": {"id": tid}}), 201
    except Exception as exc:
        logger.error("添加待办失败: %s", exc)
        return jsonify({"success": False, "message": "添加失败"}), 500


@api.route("/workplan/todo/<int:tid>/complete", methods=["PUT"])
@auth_required
@log_action("完成待办")
def complete_todo(tid):
    """标记自定义待办为已完成"""
    ok = db.complete_todo(tid)
    if ok:
        return jsonify({"success": True, "message": "已完成"}), 200
    return jsonify({"success": False, "message": "待办不存在"}), 404


@api.route("/workplan/todo/<int:tid>", methods=["DELETE"])
@auth_required
@log_action("删除待办")
def delete_todo(tid):
    """删除自定义待办"""
    ok = db.delete_todo(tid)
    if ok:
        return jsonify({"success": True, "message": "已删除"}), 200
    return jsonify({"success": False, "message": "待办不存在"}), 404

@api.route("/workplan/today", methods=["GET"])
@auth_required
@log_action("查看今日工作台")
def today_workplan():
    """获取今日工作台数据：今日待办、需要跟进的学生、日历事件"""
    try:
        data = db.get_today_workplan(counselor_id=g.user_id)
        return jsonify({"success": True, "data": data}), 200
    except Exception as exc:
        logger.error("workplan error: %s", exc)
        return jsonify({"success": True, "data": {
            "date": "",
            "weekday": "",
            "todo_list": [],
            "todo_count": 0,
            "calendar_events": [],
            "student_summary": {"total": 0, "high_risk": 0, "medium_risk": 0, "low_risk": 0},
            "pending_reminders": 0,
        }}), 200

@api.route("/workplan/complete/<int:rid>", methods=["PUT"])
@auth_required
@log_action("完成待办事项")
def complete_workplan_item(rid):
    """标记一个提醒为已完成"""
    try:
        ok = db.complete_reminder(rid)
        if ok:
            return jsonify({"success": True, "message": "已完成"}), 200
        return jsonify({"success": False, "message": "提醒不存在"}), 404
    except Exception as exc:
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500
@api.route("/workplan/day/<date_str>", methods=["GET"])
@auth_required
@log_action("查看某日待办")
def day_detail(date_str):
    """获取指定日期的详细待办列表（日历点击用）"""
    try:
        data = db.get_day_detail(date_str, counselor_id=g.user_id)
        return jsonify({"success": True, "data": data}), 200
    except Exception as exc:
        logger.error("day_detail error: %s", exc)
        return jsonify({"success": True, "data": []}), 200

@api.route("/data/export", methods=["POST"])
@auth_required
@log_action("导出数据")
def export_data():
    """导出会话记录、情绪日志或预警数据为 CSV / JSON。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供导出参数"}), 400

    export_type = data.get("type")
    output_format = data.get("format", "csv")
    date_from = data.get("date_from")
    date_to = data.get("date_to")
    college = data.get("college")

    if export_type not in ("conversations", "emotions", "alerts"):
        return jsonify({
            "success": False,
            "message": "导出类型无效，支持：conversations, emotions, alerts",
        }), 400

    if output_format not in ("csv", "json"):
        return jsonify({"success": False, "message": "导出格式无效，支持：csv, json"}), 400

    try:
        filters = {}
        if date_from:
            filters["date_from"] = date_from
        if date_to:
            filters["date_to"] = date_to
        if college:
            filters["college"] = college

        data_rows = db.export_data(export_type, filters)

        if output_format == "json":
            filename = "{}_{}.json".format(
                export_type,
                datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            )
            payload = json.dumps(data_rows, ensure_ascii=False, indent=2)
            return Response(
                payload,
                mimetype="application/json; charset=utf-8",
                headers={
                    "Content-Disposition": "attachment; filename={}".format(filename)
                },
            )
        else:
            # CSV export
            filename = "{}_{}.csv".format(
                export_type,
                datetime.utcnow().strftime("%Y%m%d_%H%M%S"),
            )
            if not data_rows:
                return jsonify({
                    "success": True,
                    "message": "没有可导出的数据",
                    "data": [],
                }), 200

            si = io.StringIO()
            writer = csv.DictWriter(si, fieldnames=data_rows[0].keys())
            writer.writeheader()
            writer.writerows(data_rows)

            output = io.BytesIO()
            output.write(si.getvalue().encode("utf-8-sig"))
            output.seek(0)

            return send_file(
                output,
                mimetype="text/csv; charset=utf-8",
                as_attachment=True,
                download_name=filename,
            )
    except Exception as exc:
        logger.error("数据导出失败: %s", exc)
        return jsonify({"success": False, "message": "数据导出失败: " + "内部错误，请稍后重试"}), 500


# ===================================================================
# 心理测评 API (PHQ-9 / GAD-7 / ISI)
# ===================================================================

@api.route("/assessment/submit", methods=["POST"])
@auth_required
def submit_assessment():
    """提交心理测评量表结果"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供测评数据"}), 400

    answers = data.get("answers", [])  # [{q:1,a:2},...]
    duration = data.get("duration_seconds", 0)
    if len(answers) < 23:
        return jsonify({"success": False, "message": "请完成全部23道题目"}), 400

    # 评分
    phq9 = sum(a.get("a", 0) for a in answers[0:9])
    gad7 = sum(a.get("a", 0) for a in answers[9:16])
    isi = sum(a.get("a", 0) for a in answers[16:23])
    item9 = answers[8].get("a", 0) if len(answers) > 8 else 0  # PHQ-9第9题

    # 分级
    def phq9_level(s): return "none" if s<=4 else ("mild" if s<=9 else ("moderate" if s<=14 else ("mod_severe" if s<=19 else "severe")))
    def gad7_level(s): return "none" if s<=4 else ("mild" if s<=9 else ("moderate" if s<=14 else "severe"))
    def isi_level(s): return "none" if s<=7 else ("mild" if s<=14 else ("moderate" if s<=21 else "severe"))

    p_level = phq9_level(phq9)
    g_level = gad7_level(gad7)
    i_level = isi_level(isi)

    # 保存
    student_pk = g.student_id if getattr(g, "user_type", "staff") == "student" else None
    if not student_pk:
        return jsonify({"success": False, "message": "仅学生可提交测评"}), 403

    try:
        rid = db.save_assessment(
            student_id=student_pk,
            phq9_score=phq9, phq9_level=p_level,
            gad7_score=gad7, gad7_level=g_level,
            isi_score=isi, isi_level=i_level,
            item9_score=item9,
            answers=json.dumps(answers, ensure_ascii=False),
            duration_seconds=duration,
        )
    except Exception as e:
        logger.error("保存测评失败: %s", e)
        return jsonify({"success": False, "message": "保存失败"}), 500

    # 分级标签中文
    labels = {"none": "正常", "mild": "轻度", "moderate": "中度", "mod_severe": "中重度", "severe": "重度"}
    # 干预建议
    suggestions = []
    if p_level in ("moderate","mod_severe","severe"):
        suggestions.append("抑郁维度建议关注，推荐预约心理咨询")
    if g_level in ("moderate","severe"):
        suggestions.append("焦虑维度偏高，建议尝试放松训练或预约心理中心")
    if i_level in ("moderate","severe"):
        suggestions.append("睡眠问题较明显，建议规律作息，必要时就医")
    if item9 >= 2:
        suggestions.append("⚠️ 第9项自伤意念得分偏高，建议辅导员立即关注并启动危机干预流程")

    result = {
        "scores": {"phq9": phq9, "gad7": gad7, "isi": isi, "item9": item9},
        "levels": {"phq9": labels[p_level], "gad7": labels[g_level], "isi": labels[i_level]},
        "suggestions": suggestions,
    }

    # 如果有高危自伤信号，通知
    if item9 >= 2:
        try:
            db.create_alert(
                student_name=getattr(g, "username", "学生"),
                student_class="",
                risk_level="high",
                emotion_type="抑郁",
                intensity=item9 * 3,
                description=f"PHQ-9第9题得分{item9}，存在自伤意念风险",
                assigned_to=None,
            )
        except Exception:
            pass

    return jsonify({"success": True, "data": result}), 200


@api.route("/assessment/history", methods=["GET"])
@auth_required
def assessment_history():
    """获取测评历史"""
    student_id = request.args.get("student_id")
    if not student_id and getattr(g, "user_type", "staff") == "student":
        student_id = g.student_id
    if not student_id:
        return jsonify({"success": False, "message": "请指定学生"}), 400
    result = db.get_assessments(student_id=int(student_id), per_page=20)
    return jsonify({"success": True, "data": result["items"], "total": result["total"]}), 200


# ===== YOLO 实时情绪识别 API =====

@api.route("/emotion/yolo-detect", methods=["POST"])
@auth_required
def yolo_detect():
    """YOLO 实时情绪检测
    接收 base64 编码的视频帧，返回面部检测和情绪分析结果
    POST body: { "image": "data:image/jpeg;base64,..." }
    """
    try:
        data = request.get_json(force=True, silent=True)
        if not data or "image" not in data:
            return jsonify({"success": False, "message": "缺少 image 参数"}), 400

        image_b64 = data["image"]
        from core.yolo_emotion import get_detector, add_alert_log
        detector = get_detector()
        result = detector.analyze_frame(image_b64)

        # 存储高危告警
        for alert in result.get("high_risk_alerts", []):
            add_alert_log(alert)
            # 同时写入数据库告警日志
            try:
                db = DatabaseManager()
                db.add_alert_log(
                    student_name=data.get("student_name", "视频监测"),
                    student_class=data.get("student_class", ""),
                    emotion_type=alert["emotion"],
                    intensity=alert["severity"],
                    risk_level="high" if alert["severity"] >= 7 else "medium",
                    details=json.dumps(alert, ensure_ascii=False)
                )
            except Exception:
                pass

        return jsonify(result), 200

    except Exception as exc:
        logger.error("YOLO 检测失败: %s", exc)
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500


@api.route("/emotion/yolo-logs", methods=["GET"])
@auth_required
def yolo_logs():
    """获取 YOLO 情绪告警记录"""
    try:
        from core.yolo_emotion import get_alert_logs
        limit = request.args.get("limit", 50, type=int)
        logs = get_alert_logs(limit)
        return jsonify({"success": True, "data": logs, "count": len(logs)}), 200
    except Exception as exc:
        logger.error("获取 YOLO 日志失败: %s", exc)
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500


@api.route("/emotion/yolo-clear", methods=["POST"])
@auth_required
def yolo_clear():
    """清空 YOLO 告警记录"""
    try:
        from core.yolo_emotion import clear_alert_logs
        clear_alert_logs()
        return jsonify({"success": True, "message": "已清空"}), 200
    except Exception as exc:
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500


# ===== 实时音频情绪分析 API =====

@api.route("/emotion/audio-chunk", methods=["POST"])
@auth_required
def analyze_audio_chunk():
    """实时音频片段情绪分析
    接收 base64 编码的音频数据，返回情绪分析结果
    POST body: { "audio": "base64...", "session_id": "video_xxx", "sample_rate": 16000 }
    """
    try:
        data = request.get_json(force=True, silent=True)
        if not data or "audio" not in data:
            return jsonify({"success": False, "message": "缺少 audio 参数"}), 400

        audio_b64 = data["audio"]
        session_id = data.get("session_id", "default")
        sample_rate = data.get("sample_rate", 16000)

        analyzer = get_or_create_analyzer(session_id)
        result = analyzer.analyze_chunk(audio_b64, sample_rate)

        # 检查是否需要告警
        should_alert = analyzer.should_alert

        return jsonify({
            "success": True,
            "data": result,
            "should_alert": should_alert,
        }), 200

    except Exception as exc:
        logger.error("实时音频分析失败: %s", exc)
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500


@api.route("/emotion/realtime-summary", methods=["GET"])
@auth_required
def realtime_summary():
    """获取实时情绪分析会话总结
    Query params: session_id (required)
    """
    try:
        session_id = request.args.get("session_id", "default")
        analyzer = get_or_create_analyzer(session_id)
        summary = analyzer.get_summary()
        return jsonify({"success": True, "data": summary}), 200
    except Exception as exc:
        logger.error("获取实时情绪总结失败: %s", exc)
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500


@api.route("/emotion/realtime-reset", methods=["POST"])
@auth_required
def realtime_reset():
    """重置实时情绪分析会话
    POST body: { "session_id": "video_xxx" }
    """
    try:
        data = request.get_json(silent=True) or {}
        session_id = data.get("session_id", "default")
        cleanup_session(session_id)
        return jsonify({"success": True, "message": f"会话 {session_id} 已重置"}), 200
    except Exception as exc:
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500


# ===== 系统管理工具 API =====

@api.route("/system/reseed", methods=["POST"])
@role_required(["super_admin"])
def system_reseed():
    """重新生成测试数据（仅管理员）"""
    import subprocess, os
    try:
        result = subprocess.run(
            ["python", "seed_v31.py"],
            cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            capture_output=True, text=True, timeout=120
        )
        if result.returncode == 0:
            return jsonify({"success": True, "message": "测试数据已重新生成，请刷新页面"}), 200
        else:
            logger.error("reseed failed: %s", result.stderr)
            return jsonify({"success": False, "message": "生成失败: " + result.stderr[-200:]}), 500
    except Exception as exc:
        return jsonify({"success": False, "message": "内部错误，请稍后重试"}), 500
