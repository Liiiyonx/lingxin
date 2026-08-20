from core.realtime_emotion import get_or_create_analyzer, cleanup_session

from api import common
from api.common import *  # noqa: F401,F403
from api.common import api, logger, auth_required, role_required, log_action
from api.common import (
    _check_login_rate_limit,
    _audit_login_failure,
    _validate_password_strength,
    _fallback_knowledge_search,
)

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
                common.db = DatabaseManager()
                common.db.add_alert_log(
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
