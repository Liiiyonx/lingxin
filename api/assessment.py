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
        rid = common.db.save_assessment(
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

    # 将测评结果回写学生档案，普通中高风险不再只静默落库。
    if p_level in ("mod_severe", "severe") or g_level == "severe" or i_level == "severe":
        assessment_risk = "high"
    elif p_level in ("mild", "moderate") or g_level in ("mild", "moderate") or i_level in ("mild", "moderate"):
        assessment_risk = "medium"
    else:
        assessment_risk = "low"
    if item9 >= 2:
        assessment_risk = "high"
        assessment_emotion = "自伤风险"
    elif assessment_risk == "high":
        assessment_emotion = "重度心理困扰"
    elif assessment_risk == "medium":
        assessment_emotion = "情绪需关注"
    else:
        assessment_emotion = "正常"
    try:
        common.db.update_student_state_from_evidence(
            student_id=student_pk,
            risk_level=assessment_risk,
            emotion_status=assessment_emotion,
            source="assessment",
            counselor_id=common.db.get_student_by_id(student_pk).get("counselor_id") if common.db.get_student_by_id(student_pk) else None,
            description="测评结果已回写，请根据风险等级安排后续跟进。",
        )
    except Exception as exc:
        logger.warning("测评状态回写失败: %s", exc)

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
        "crisis": item9 >= 2,
        "crisis_hotline": "全国心理援助热线 400-161-9995 · 北京危机干预 010-82951332",
    }

    # 如果有高危自伤信号，触发危机干预（生成高危预警 + 审计 + 关联学生）
    if item9 >= 2:
        try:
            stu = common.db.get_student_by_id(student_pk) if student_pk else None
            common.db.create_alert(
                student_name=stu.get("name") if stu else getattr(g, "username", "学生"),
                student_class=stu.get("class_name") if stu else "",
                risk_level="high",
                emotion_type="危机",
                intensity=10,
                description=f"PHQ-9第9题得分{item9}，存在自伤意念风险，需立即启动危机干预",
                assigned_to=stu.get("counselor_id") if stu else None,
                student_id=student_pk,
            )
            common.db.log_action(student_pk, "危机预警", target_type="assessment", details={"item9": item9, "phq9": phq9})
        except Exception as exc:
            logger.warning("危机预警创建失败: %s", exc)

    return jsonify({"success": True, "data": result}), 200


@api.route("/crisis/report", methods=["POST"])
@auth_required
@log_action("危机上报")
def crisis_report():
    """危机上报：学生/辅导员主动上报心理危机，生成高危预警并关联学生、广播通知。"""
    data = request.get_json(silent=True) or {}
    reason = (data.get("reason") or "").strip()
    is_student = getattr(g, "user_type", "staff") == "student"

    student_pk = g.student_id if is_student else None
    student_name = getattr(g, "username", "学生")
    student_class = ""
    student_id_no = ""
    counselor_id = None

    # 辅导员/管理员上报时，通过学号解析学生
    if not is_student:
        sid_str = str(data.get("student_id") or "").strip()
        if sid_str.isdigit():
            stu = common.db.get_student_by_student_id(sid_str)
            if stu:
                student_pk = stu.get("id")

    if student_pk:
        stu = common.db.get_student_by_id(student_pk)
        if stu:
            student_name = stu.get("name") or student_name
            student_class = stu.get("class_name") or ""
            student_id_no = stu.get("student_id") or ""
            counselor_id = stu.get("counselor_id")

    try:
        alert_id = common.db.create_alert(
            student_name=student_name,
            student_class=student_class,
            risk_level="high",
            emotion_type="危机",
            intensity=10,
            description=f"危机上报：{reason or '学生主动求助'}",
            assigned_to=counselor_id,
            student_id=student_pk,
        )
        common.db.log_action(
            g.user_id if not is_student else student_pk,
            "危机上报",
            target_type="crisis",
            target_id=alert_id,
            details={"reason": reason, "student_name": student_name, "student_id": student_id_no},
        )
    except Exception as exc:
        logger.error("危机上报失败: %s", exc)
        return jsonify({"success": False, "message": "危机上报失败，请稍后重试"}), 500

    return jsonify({
        "success": True,
        "message": "已上报，辅导员与心理中心将尽快联系你，请保持安全",
        "data": {
            "alert_id": alert_id,
            "hotline": "全国心理援助热线 400-161-9995 · 北京危机干预 010-82951332",
        },
    }), 200


@api.route("/assessment/history", methods=["GET"])
@auth_required
def assessment_history():
    """获取测评历史"""
    student_id = request.args.get("student_id")
    if not student_id and getattr(g, "user_type", "staff") == "student":
        student_id = g.student_id
    if not student_id:
        return jsonify({"success": False, "message": "请指定学生"}), 400
    result = common.db.get_assessments(student_id=int(student_id), per_page=20)
    return jsonify({"success": True, "data": result["items"], "total": result["total"]}), 200
