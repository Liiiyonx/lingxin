from api import common
from api.common import *  # noqa: F401,F403
from api.common import api, logger, auth_required, role_required, log_action
from api.common import (
    _check_login_rate_limit,
    _audit_login_failure,
    _validate_password_strength,
    _fallback_knowledge_search,
)

# ===================================================================
# 4. 预警管理路由 (Alert Routes)
# ===================================================================

@api.route("/alert/list", methods=["GET"])
@role_required(["counselor", "super_admin", "student_affairs"])
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

        assigned_to = g.user_id if g.role == "counselor" else None
        result = common.db.search_alerts(
            student_name=request.args.get("student_name"),
            risk_level=filters.get("risk_level"),
            status=filters.get("status"),
            assigned_to=assigned_to,
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
@role_required(["counselor", "super_admin", "student_affairs"])
@log_action("确认预警")
def acknowledge_alert(alert_id):
    """将预警标记为已确认。"""
    try:
        existing = common.db.get_alert(alert_id)
        if existing is None:
            return jsonify({"success": False, "message": "预警记录不存在"}), 404

        if existing.get("status") == "acknowledged":
            return jsonify({"success": False, "message": "该预警已被确认"}), 400

        common.db.update_alert(alert_id, {
            "status": "acknowledged",
            "acknowledged_by": g.user_id,
            "acknowledged_at": datetime.utcnow(),
        })
        return jsonify({"success": True, "message": "预警已确认"}), 200
    except Exception as exc:
        logger.error("确认预警失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/alert/<int:alert_id>/resolve", methods=["PUT"])
@role_required(["counselor", "super_admin", "student_affairs"])
@log_action("解决预警")
def resolve_alert(alert_id):
    """将预警标记为已解决。"""
    data = request.get_json(silent=True) or {}

    try:
        existing = common.db.get_alert(alert_id)
        if existing is None:
            return jsonify({"success": False, "message": "预警记录不存在"}), 404

        updates = {
            "status": "resolved",
            "resolved_by": g.user_id,
            "resolved_at": datetime.utcnow(),
        }
        resolution = data.get("resolution")
        if resolution:
            updates["resolution"] = resolution

        common.db.update_alert(alert_id, updates)
        if existing.get("student_id"):
            common.db.refresh_student_risk_after_alert_resolution(existing["student_id"])
        return jsonify({"success": True, "message": "预警已解决"}), 200
    except Exception as exc:
        logger.error("解决预警失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/alert/crisis-center", methods=["GET"])
@role_required(["super_admin", "student_affairs"])
@log_action("查看危机工单中心")
def crisis_center_alerts():
    """心理中心/学工处跨辅导员查看所有危机预警。"""
    try:
        page = max(1, request.args.get("page", 1, type=int))
        per_page = min(100, max(1, request.args.get("per_page", 20, type=int)))
        escalated = request.args.get("escalated")
        if escalated is not None:
            escalated = escalated.lower() in ("1", "true", "yes")
        result = common.db.search_alerts(
            emotion_type="危机",
            status=request.args.get("status"),
            risk_level=request.args.get("risk_level"),
            assigned_to=request.args.get("assigned_to", type=int) or None,
            escalated=escalated,
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
            },
        }), 200
    except Exception as exc:
        logger.error("获取危机工单中心失败: %s", exc)
        return jsonify({"success": False, "message": "获取危机工单中心失败"}), 500


@api.route("/alert/crisis-center/<int:alert_id>/assign", methods=["PUT"])
@role_required(["super_admin", "student_affairs"])
@log_action("指派危机工单")
def assign_crisis_alert(alert_id):
    """学工处/管理员将危机工单指派给具体辅导员。"""
    data = request.get_json(silent=True) or {}
    try:
        existing = common.db.get_alert(alert_id)
        if existing is None:
            return jsonify({"success": False, "message": "危机工单不存在"}), 404
        assigned_to = data.get("assigned_to")
        if not isinstance(assigned_to, int) or assigned_to <= 0:
            return jsonify({"success": False, "message": "请选择有效辅导员"}), 400
        updates = {"assigned_to": assigned_to}
        if not existing.get("escalated"):
            updates.update({
                "escalated": True,
                "escalated_by": g.user_id,
                "escalated_at": datetime.utcnow(),
                "escalation_note": data.get("note") or "学工处/心理中心已指派危机处置人",
            })
        common.db.update_alert(alert_id, updates)
        return jsonify({"success": True, "message": "危机工单已指派"}), 200
    except Exception as exc:
        logger.error("指派危机工单失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/alert/crisis-center/<int:alert_id>/close", methods=["PUT"])
@role_required(["super_admin", "student_affairs"])
@log_action("关闭危机工单")
def close_crisis_alert(alert_id):
    """学工处/管理员关闭危机工单，并重算学生风险状态。"""
    data = request.get_json(silent=True) or {}
    try:
        existing = common.db.get_alert(alert_id)
        if existing is None:
            return jsonify({"success": False, "message": "危机工单不存在"}), 404
        if existing.get("status") == "resolved":
            return jsonify({"success": False, "message": "该危机工单已关闭"}), 400
        common.db.update_alert(alert_id, {
            "status": "resolved",
            "resolved_by": g.user_id,
            "resolved_at": datetime.utcnow(),
            "resolution": (data.get("resolution") or "危机工单已由学工处/心理中心关闭").strip(),
        })
        if existing.get("student_id"):
            common.db.refresh_student_risk_after_alert_resolution(existing["student_id"])
        return jsonify({"success": True, "message": "危机工单已关闭"}), 200
    except Exception as exc:
        logger.error("关闭危机工单失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/alert/<int:alert_id>/escalate", methods=["PUT"])
@role_required(["counselor", "super_admin", "student_affairs"])
@log_action("升级危机预警")
def escalate_alert(alert_id):
    """将预警升级到心理中心/学工处，跨角色可见。"""
    data = request.get_json(silent=True) or {}
    try:
        existing = common.db.get_alert(alert_id)
        if existing is None:
            return jsonify({"success": False, "message": "预警记录不存在"}), 404
        common.db.update_alert(alert_id, {
            "escalated": True,
            "escalated_by": g.user_id,
            "escalated_at": datetime.utcnow(),
            "escalation_note": data.get("note") or "预警升级至心理中心/学工处协同处置",
        })
        return jsonify({"success": True, "message": "预警已升级"}), 200
    except Exception as exc:
        logger.error("升级危机预警失败: %s", exc)
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

        stats = common.db.get_alert_statistics(**params)
        return jsonify({"success": True, "data": stats}), 200
    except Exception as exc:
        logger.error("获取预警统计失败: %s", exc)
        return jsonify({"success": False, "message": "获取预警统计失败"}), 500
