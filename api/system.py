import os

from api import common
from api.common import *  # noqa: F401,F403
from api.common import api, logger, auth_required, role_required, log_action
from api.common import (
    _check_login_rate_limit,
    _audit_login_failure,
    _validate_password_strength,
    _fallback_knowledge_search,
)

@api.route("/system/test-accounts", methods=["GET"])
def test_accounts():
    """动态下发测试账号列表（辅导员 + 学生），供登录页渲染，避免硬编码错位。"""
    try:
        accounts = common.db.get_test_accounts()
        return jsonify({"success": True, "data": accounts}), 200
    except Exception as exc:
        logger.error("获取测试账号失败: %s", exc)
        return jsonify({"success": False, "message": "获取测试账号失败"}), 500

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

        result = common.db.get_system_logs(filters=filters, page=page, per_page=per_page)

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
        total_conversations = common.db.get_statistics().get("total_conversations", 0)
        total_emotions = common.db.get_statistics().get("total_emotion_logs", 0)
        stats = common.db.get_statistics()
        pending_alerts = stats.get("pending_alerts", 0)
        resolved_alerts = stats.get("resolved_alerts", 0)

        emotion_logs = common.db.get_emotion_logs(page=1, per_page=10000)
        emo_items = emotion_logs.get("items", [])
        emo_counts = Counter(item.get("emotion", "unknown") for item in emo_items)
        total_emo = len(emo_items) if emo_items else 1
        emotion_dist = {k: round(v / total_emo * 100) for k, v in emo_counts.most_common(6)}

        # 汇总风险等级分布
        alert_result_all = common.db.search_alerts(page=1, per_page=10000)
        all_alerts = alert_result_all.get("items", [])
        risk_counts = Counter(a.get("risk_level", "low") for a in all_alerts)
        risk_distribution = {
            "high": risk_counts.get("high", 0),
            "medium": risk_counts.get("medium", 0),
            "low": risk_counts.get("low", 0),
        }

        # 汇总最近 7 天情绪趋势
        from datetime import datetime as _dt, timedelta as _td
        today = _dt.now()
        trend_data = []
        for i in range(6, -1, -1):
            day = today - _td(days=i)
            day_str = day.strftime("%m-%d")
            day_emo = [e for e in emo_items
                       if e.get("created_at", "")[:10] == day.strftime("%Y-%m-%d")]
            trend_data.append({"date": day_str, "count": len(day_emo)})

        alert_result = common.db.search_alerts(page=1, per_page=5)
        recent_alerts = [
            {"id": a.get("id"), "student_name": a.get("student_name"), "emotion_type": a.get("emotion_type"),
             "intensity": a.get("intensity"), "risk_level": a.get("risk_level"), "status": a.get("status"),
             "created_at": a.get("created_at", "")}
            for a in alert_result.get("items", [])
        ]

        # 知识库文档数：优先读向量库文档级索引，未配置 key 时退回 docs/ 目录文件计数
        kb_docs = 0
        kb = common.knowledge_base
        if kb is not None:
            try:
                kb_docs = len(getattr(kb, "_doc_index", {}) or {})
            except Exception:
                kb_docs = 0
        if not kb_docs:
            try:
                docs_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "docs")
                if os.path.isdir(docs_dir):
                    kb_docs = len([
                        f for f in os.listdir(docs_dir)
                        if os.path.isfile(os.path.join(docs_dir, f))
                        and os.path.splitext(f)[1].lower() in {".pdf", ".txt", ".docx", ".doc", ".md", ".csv"}
                    ])
            except Exception:
                kb_docs = 0

        return jsonify({
            "conversations": total_conversations,
            "emotions": total_emotions,
            "alerts_pending": pending_alerts,
            "alerts_resolved": resolved_alerts,
            "knowledge_docs": kb_docs,
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
