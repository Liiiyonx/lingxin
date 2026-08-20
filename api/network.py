from api import common
from api.common import *  # noqa: F401,F403
from api.common import api, logger, auth_required, role_required, log_action
from api.common import (
    _check_login_rate_limit,
    _audit_login_failure,
    _validate_password_strength,
    _fallback_knowledge_search,
)

@api.route("/network/emotion-graph", methods=["GET"])
@auth_required
@log_action("查看情绪网络图")
def emotion_network_graph():
    """获取情绪网络图数据：中心 → 情绪分支 → 学生节点（按严重程度着色）。"""
    try:
        role = getattr(g, "role", None)
        cid = g.user_id if role == "counselor" else None
        data = common.db.get_emotion_network(counselor_id=cid, role=role)
        return jsonify({"success": True, "data": data}), 200
    except Exception as exc:
        logger.error("获取情绪网络图失败: %s", exc)
        return jsonify({"success": False, "message": "获取网络图数据失败"}), 500
