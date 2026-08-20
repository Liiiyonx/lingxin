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
        student_id = data.get("student_id")
        if student_id in (None, "", 0):
            student_id = None
        else:
            student_id = int(student_id)
        tid = common.db.create_todo(
            user_id=g.user_id,
            title=data["title"],
            description=data.get("description", ""),
            category=data.get("category", "work_task"),
            priority=data.get("priority", "medium"),
            due_date=data.get("due_date"),
            student_id=student_id,
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
    meta = common.db.complete_todo(tid)
    if meta is not None:
        if meta.get("category") == "student_care" and meta.get("student_id"):
            try:
                common.db.update_student_state_from_evidence(
                    student_id=meta.get("student_id"),
                    risk_level="low",
                    emotion_status="已跟进",
                    source="todo_done",
                    counselor_id=meta.get("user_id"),
                    description=f"学生关注待办「{meta.get('title') or '学生跟进'}」已完成",
                )
            except Exception as exc:
                logger.warning("待办完成后的学生状态回写失败: %s", exc)
        return jsonify({"success": True, "message": "已完成"}), 200
    return jsonify({"success": False, "message": "待办不存在"}), 404


@api.route("/workplan/todo/<int:tid>", methods=["DELETE"])
@auth_required
@log_action("删除待办")
def delete_todo(tid):
    """删除自定义待办"""
    ok = common.db.delete_todo(tid)
    if ok:
        return jsonify({"success": True, "message": "已删除"}), 200
    return jsonify({"success": False, "message": "待办不存在"}), 404

@api.route("/workplan/today", methods=["GET"])
@auth_required
@log_action("查看今日工作台")
def today_workplan():
    """获取今日工作台数据：今日待办、需要跟进的学生、日历事件"""
    try:
        data = common.db.get_today_workplan(counselor_id=g.user_id)
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
                        description="工作台提醒已完成，学生状态已同步跟进记录",
                    )
                except Exception as exc:
                    logger.warning("工作台提醒完成后的学生状态回写失败: %s", exc)
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
        data = common.db.get_day_detail(date_str, counselor_id=g.user_id)
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

        data_rows = common.db.export_data(export_type, filters)

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
