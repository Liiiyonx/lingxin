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

    if common.emotion_analyzer is None:
        return jsonify({"success": False, "message": "情绪分析引擎未初始化，请检查模型配置"}), 503

    try:
        # Save uploaded file to a temp path for the engine
        suffix = os.path.splitext(audio_file.filename)[1].lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            audio_file.save(tmp.name)
            tmp_path = tmp.name

        try:
            result = common.emotion_analyzer.analyze_single(tmp_path)
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

        common.db.create_emotion_log(
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
            common.db.create_alert(
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
        result = common.emotion_analyzer.batch_analyze(audio_paths)
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
        result = common.db.get_emotion_logs(
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
        log_id = common.db.create_emotion_log(
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
            common.db.create_alert(
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

        student = common.db.find_student_for_realtime_summary(
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

        log_id = common.db.create_emotion_log(
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
            profile_id = common.db.create_student_profile(
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
            emotion_tracking_id = common.db.create_emotion_tracking(
                student_id=sid,
                emotion=peak_emotion,
                intensity=review_score,
                risk_level=risk_level,
                source="video_call_summary",
                notes=summary,
                recorded_by=analyzer_id,
                auto_reminder=False,
            )
            common.db.update_student_state_from_evidence(
                student_id=sid,
                risk_level=risk_level,
                emotion_status=peak_emotion,
                source="video_call_summary",
                counselor_id=analyzer_id,
                description="视频通话情绪总结已回写学生状态",
            )
            reminder_id = common.db.create_realtime_followup_reminder(
                student_id=sid,
                counselor_id=analyzer_id,
                title="\u3010{}\u3011{} \u89c6\u9891\u901a\u8bdd\u540e\u60c5\u7eea\u590d\u67e5".format(rule["label"], student_name),
                description=summary + " \u590d\u67e5\u89c4\u5219\uff1a" + _format_realtime_rule_text(),
                priority=rule["priority"],
                due_date=follow_up_date,
            )

        if risk_level in ("high", "critical"):
            common.db.create_alert(
                student_name=student_name,
                student_class=student_class,
                risk_level="high",
                emotion_type=peak_emotion,
                intensity=review_score,
                description=summary + " \u5efa\u8bae\u590d\u67e5\u65f6\u95f4\uff1a{}\u3002".format(follow_up_date.strftime("%Y-%m-%d")),
                assigned_to=analyzer_id,
            )

        # \u901a\u8bdd\u7ed3\u675f\u3001\u5b66\u751f\u60c5\u7eea\u72b6\u6001\u5df2\u843d\u5e93 \u2192 \u5e7f\u64ad\u7f51\u7edc\u56fe\u5237\u65b0\u4e8b\u4ef6\uff08\u8de8\u7aef\u5b9e\u65f6\u8054\u52a8\uff09
        common.emit_network_graph_update(student_name=student_name)

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
        existing = common.db.get_emotion_logs(page=1, per_page=10000).get("items", [])
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
            common.db.create_emotion_log(
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
                common.db.create_alert(
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
                payload = common.auth.verify_token(auth_header[7:])
                if payload and isinstance(payload, dict) and payload.get("role") == "counselor":
                    cid = payload.get("user_id")
            except Exception:
                pass
        params = {k: v for k, v in params.items() if v is not None}
        stats = common.db.get_emotion_statistics(counselor_id=cid, **params)
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
        if getattr(g, "user_type", "staff") == "student":
            student_id = g.student_id

        trends = common.db.get_emotion_trends(
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

        heatmap = common.db.get_emotion_heatmap(
            date_from=date_from,
            date_to=date_to,
            college=college,
        )
        return jsonify({"success": True, "data": heatmap}), 200
    except Exception as exc:
        logger.error("获取热力图数据失败: %s", exc)
        return jsonify({"success": False, "message": "获取热力图数据失败"}), 500
