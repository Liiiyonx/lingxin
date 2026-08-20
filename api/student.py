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
    result = common.db.get_students(page=page, per_page=per_page, filters=filters, counselor_id=counselor_id)
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
        sid = common.db.create_student(
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
    with common.db.get_session() as session:
        from core.database import Student
        s = session.query(Student).get(sid)
        if not s:
            return jsonify({"success": False, "message": "学生不存在"}), 404
        return jsonify({"success": True, "data": common.db._to_dict(s)}), 200


@api.route("/student/<int:sid>", methods=["PUT"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("更新学生信息")
def update_student(sid):
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请提供更新数据"}), 400
    if "risk_level" in data or "emotion_status" in data:
        return jsonify({
            "success": False,
            "message": "风险状态请使用 /student/<sid>/risk 人工调整接口，避免绕过证据时间线",
        }), 400
    allowed = {"name", "gender", "college", "class_name", "phone", "notes"}
    updates = {k: v for k, v in data.items() if k in allowed}
    if not updates:
        return jsonify({"success": False, "message": "没有可更新的字段"}), 400
    ok = common.db.update_student(sid, updates)
    if ok:
        return jsonify({"success": True, "message": "更新成功"}), 200
    return jsonify({"success": False, "message": "学生不存在"}), 404


@api.route("/student/<int:sid>/risk", methods=["PUT"])
@role_required(["counselor", "super_admin", "student_affairs"])
@log_action("人工调整学生风险等级")
def manually_adjust_student_risk(sid):
    """辅导员/学工处显式调整学生风险等级，支持降级并记录审计。"""
    data = request.get_json(silent=True) or {}
    allowed = {"none", "low", "medium", "high", "critical",
               "normal", "mild", "moderate", "severe",
               "轻度", "中度", "中重度", "重度", "危急", "危机"}
    risk_level = data.get("risk_level")
    if not risk_level or risk_level not in allowed:
        return jsonify({"success": False, "message": "风险等级无效"}), 400
    try:
        updated = common.db.manually_set_student_risk(
            student_id=sid,
            risk_level=risk_level,
            operator_id=g.user_id,
            emotion_status=(data.get("emotion_status") or "人工调整").strip(),
            reason=(data.get("reason") or "人工调整风险等级").strip(),
        )
        if updated is None:
            return jsonify({"success": False, "message": "学生不存在"}), 404
        return jsonify({"success": True, "message": "风险等级已更新", "data": updated}), 200
    except Exception as exc:
        logger.error("人工调整学生风险等级失败: %s", exc)
        return jsonify({"success": False, "message": "操作失败，请稍后重试"}), 500


@api.route("/student/<int:sid>/risk-timeline", methods=["GET"])
@role_required(["counselor", "super_admin", "student_affairs"])
@log_action("查看学生风险时间线")
def get_student_risk_timeline(sid):
    """返回学生风险证据时间线，解释当前风险等级的来源。"""
    try:
        timeline = common.db.get_student_risk_timeline(sid)
        return jsonify({"success": True, "data": timeline}), 200
    except Exception as exc:
        logger.error("获取学生风险时间线失败: %s", exc)
        return jsonify({"success": False, "message": "获取风险时间线失败"}), 500


@api.route("/student/<int:sid>/profiles", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看学生档案")
def get_student_profiles(sid):
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(50, request.args.get("per_page", 20, type=int))
    result = common.db.get_student_profiles(sid, page=page, per_page=per_page)
    return jsonify({"success": True, "data": result["items"], "total": result["total"]}), 200


@api.route("/student/<int:sid>/profile/add", methods=["POST"])
@auth_required
@log_action("添加学生档案")
def add_student_profile(sid):
    data = request.get_json(silent=True)
    if not data or not data.get("summary"):
        return jsonify({"success": False, "message": "请提供谈话摘要"}), 400
    try:
        pid = common.db.create_student_profile(
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
        eid = common.db.create_emotion_tracking(
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
    data = common.db.get_emotion_tracking(sid, days=days)
    return jsonify({"success": True, "data": data}), 200


@api.route("/student/reminder/list", methods=["GET"])
@role_required(["super_admin", "student_affairs", "counselor"])
@log_action("查看提醒列表")
def list_reminders():
    page = max(1, request.args.get("page", 1, type=int))
    per_page = min(100, request.args.get("per_page", 50, type=int))
    result = common.db.get_reminders(counselor_id=g.user_id, page=page, per_page=per_page)
    return jsonify({"success": True, "data": result["items"], "total": result["total"]}), 200


@api.route("/student/reminder/<int:rid>/complete", methods=["PUT"])
@auth_required
@log_action("完成提醒")
def complete_reminder_route(rid):
    meta = common.db.complete_reminder(rid)
    if meta is not None:
        reminder_type = meta.get("reminder_type") or ""
        if reminder_type == "emotion_check" or reminder_type.endswith("_followup"):
            try:
                common.db.update_student_state_from_evidence(
                    student_id=meta.get("student_id"),
                    risk_level="low",
                    emotion_status="已跟进",
                    source="reminder_done",
                    counselor_id=meta.get("counselor_id"),
                    description="提醒已完成，学生状态已同步跟进记录",
                )
            except Exception as exc:
                logger.warning("提醒完成后的学生状态回写失败: %s", exc)
        return jsonify({"success": True, "message": "提醒已完成"}), 200
    return jsonify({"success": False, "message": "提醒不存在"}), 404


@api.route("/student/stats", methods=["GET"])
@auth_required
@log_action("查看学生统计")
def student_stats():
    stats = common.db.get_student_stats()
    return jsonify({"success": True, "data": stats}), 200


@api.route("/student/calendar", methods=["GET"])
@auth_required
@log_action("查看日历事件")
def calendar_events():
    year = request.args.get("year", datetime.utcnow().year, type=int)
    month = request.args.get("month", datetime.utcnow().month, type=int)
    events = common.db.get_calendar_events(year, month)
    return jsonify({"success": True, "data": events}), 200

# ===================================================================
# 辅导员列表 API（供学生预约选择）
# ===================================================================

@api.route("/counselors/list", methods=["GET"])
@auth_required
def list_counselors():
    """获取所有辅导员列表（供学生预约选择）"""
    try:
        counselors = common.db.get_counselors()
        return jsonify({"success": True, "data": counselors}), 200
    except Exception as exc:
        logger.error("获取辅导员列表失败: %s", exc)
        return jsonify({"success": False, "message": "获取失败"}), 500
