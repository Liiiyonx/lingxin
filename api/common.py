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
import threading
import time
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
from core.digital_human import generate_reply, digital_human_status
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


def _audit_login_failure(username, ip, kind="staff"):
    """记录登录失败审计日志（不抛异常，避免影响登录主流程）"""
    try:
        db.log_action(
            None,
            "登录失败" if kind == "staff" else "学生登录失败",
            target_type="auth",
            details={"username": username, "ip": ip},
            ip_address=ip,
        )
    except Exception as exc:
        logger.warning("登录失败审计记录失败: %s", exc)


def _validate_password_strength(password, student_id=""):
    """密码强度校验：至少6位、不能纯数字、不能与学号相同。返回 (是否通过, 提示)"""
    if len(password) < 6:
        return False, "密码长度至少6位"
    if password.isdigit():
        return False, "密码不能为纯数字，请包含字母"
    if student_id and password == student_id:
        return False, "密码不能与学号相同"
    return True, ""

# Module-level singletons (lazy-initialised after app starts)
db = None
auth = None
emotion_analyzer = None
risk_alert = None
conversation_engine = None
prompt_manager = None
knowledge_base = None
rag_generator = None
_socketio = None


def set_socketio(sio):
    """由 app.py 在创建 SocketIO 后注入，供路由实时推送事件。"""
    global _socketio
    _socketio = sio


def emit_network_graph_update(student_name=None):
    """视频通话情绪总结落库后，广播网络图刷新事件（跨用户实时联动）。"""
    if _socketio is None:
        return
    try:
        _socketio.emit("emotion_graph_update", {
            "student_name": student_name or "",
            "ts": datetime.now().isoformat(),
        })
    except Exception as exc:
        logger.warning("网络图刷新事件推送失败: %s", exc)


def emit_alert_created(alert):
    """向辅导员/学工处广播新预警，供前端即时刷新并提示。"""
    if _socketio is None or not alert:
        return
    try:
        _socketio.emit("alert_created", alert)
    except Exception as exc:
        logger.warning("预警实时推送失败: %s", exc)


def emit_new_message(room, message):
    """向指定聊天房间实时推送消息。"""
    if _socketio is None:
        return
    try:
        _socketio.emit("new_message", message, room=room)
    except Exception as exc:
        logger.warning("新消息实时推送失败: %s", exc)


def emit_conversation_message(message):
    """把一条会话消息推送到教师收件箱和对应学生的专属会话房间。"""
    if not message:
        return
    student_id = message.get("student_id")
    counselor_id = message.get("counselor_id")
    if student_id is None or counselor_id is None:
        return
    rooms = [
        f"teacher_chat_{counselor_id}",
        f"student_chat_{student_id}_{counselor_id}",
    ]
    for room in rooms:
        emit_new_message(room, message)


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
