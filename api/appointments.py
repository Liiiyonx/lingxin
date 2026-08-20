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

    result = common.db.get_appointments(user_id, user_type, status, page, per_page)

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

    appt_id = common.db.create_appointment(student_id, counselor_id, appt_time, reason, duration)

    return jsonify({
        "success": True,
        "message": "预约创建成功",
        "data": {"id": appt_id},
    }), 200


@api.route("/appointments/<int:appt_id>/status", methods=["PUT"])
@role_required(["counselor", "super_admin", "student_affairs"])
def update_appointment_status(appt_id):
    """更新预约状态"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效"}), 400

    status = data.get("status")
    notes = data.get("notes")

    if status not in ["pending", "confirmed", "completed", "cancelled"]:
        return jsonify({"success": False, "message": "无效的状态"}), 400

    existing = common.db.get_appointment(appt_id)
    if existing is None:
        return jsonify({"success": False, "message": "预约不存在"}), 404

    previous_status = existing.get("status")
    common.db.update_appointment_status(appt_id, status, notes)

    # confirmed：自动进入辅导员待办；completed：沉淀为谈心记录。
    try:
        if status == "confirmed" and previous_status != "confirmed":
            counselor_id = existing.get("counselor_id")
            student_name = existing.get("student_name") or "学生"
            appointment_time = existing.get("appointment_time") or ""
            reason = existing.get("reason") or "视频咨询"
            duration = existing.get("duration") or 30
            try:
                due_datetime = datetime.fromisoformat(str(appointment_time).replace('Z', '+00:00'))
            except Exception:
                due_datetime = None
            common.db.create_todo(
                user_id=counselor_id,
                title=f"预约：{student_name} - {reason}",
                description=f"预约时间 {appointment_time}，预计 {duration} 分钟。",
                category="appointment",
                priority="medium",
                due_date=due_datetime,
                student_id=existing.get("student_id"),
            )
        elif status == "completed":
            student_id = existing.get("student_id")
            appointment_time = existing.get("appointment_time") or ""
            reason = existing.get("reason") or "视频咨询"
            summary = f"预约完成：{reason}（{appointment_time}）"
            if notes:
                summary += f"\n备注：{notes}"
            common.db.create_student_profile(
                student_id=student_id,
                counselor_id=existing.get("counselor_id"),
                record_type="appointment_completed",
                summary=summary,
                structured_content=json.dumps({
                    "appointment_time": appointment_time,
                    "reason": reason,
                    "notes": notes or "",
                }, ensure_ascii=False),
                emotion_tags=None,
                risk_level="low",
                counselor_impression="预约完成自动沉淀，建议补充具体谈心记录。",
            )
    except Exception as exc:
        logger.error("预约状态联动失败: %s", exc)

    return jsonify({
        "success": True,
        "message": "预约状态已更新",
    }), 200
