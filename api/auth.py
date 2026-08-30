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
# 1. 认证路由 (Auth Routes)
# ===================================================================

@api.route("/auth/login", methods=["POST"])
def login():
    """用户登录，返回 JWT 令牌。"""
    ip = request.remote_addr or 'unknown'
    if not _check_login_rate_limit(ip):
        return jsonify({"success": False, "message": "登录尝试过于频繁，请5分钟后再试"}), 429
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效，请提供 JSON 数据"}), 400

    username = (data.get("username") or "").strip()
    password = (data.get("password") or "").strip()

    if not username or not password:
        return jsonify({"success": False, "message": "用户名和密码不能为空"}), 400

    try:
        user = common.auth.authenticate(username, password)
    except Exception as exc:
        logger.error("认证过程异常: %s", exc)
        return jsonify({"success": False, "message": "登录失败，请稍后重试"}), 500

    if user is None:
        _audit_login_failure(username, ip, kind="staff")
        return jsonify({"success": False, "message": "用户名或密码错误"}), 401

    # 顶号登录：覆盖旧会话并吊销旧 token，不再拒绝第二次登录
    common.auth.supersede_session("staff", user["username"])
    token = common.auth.generate_token(user)
    common.auth.register_session("staff", user["username"], token)

    return jsonify({
        "success": True,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": {
                "user_id": user.get("id"),
                "username": user.get("username"),
                "role": user.get("role"),
                "display_name": user.get("display_name"),
                "college": user.get("college"),
            },
        },
    }), 200


@api.route("/auth/logout", methods=["POST"])
@auth_required
@log_action("用户登出")
def logout():
    """注销当前令牌。"""
    auth_header = request.headers.get("Authorization", "")
    token = auth_header[7:] if auth_header.startswith("Bearer ") else None

    try:
        if token:
            common.auth.revoke_token(token)
            common.auth.clear_session(token)
    except Exception as exc:
        logger.error("令牌注销失败: %s", exc)

    return jsonify({"success": True, "message": "已成功退出登录"}), 200


# ===================================================================
# 学生登录 API
# ===================================================================

@api.route("/student/login", methods=["POST"])
def student_login():
    """学生登录，返回 JWT 令牌。"""
    ip = request.remote_addr or 'unknown'
    if not _check_login_rate_limit(ip):
        return jsonify({"success": False, "message": "登录尝试过于频繁，请5分钟后再试"}), 429
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效，请提供 JSON 数据"}), 400

    student_id = (data.get("student_id") or "").strip()
    password = (data.get("password") or "").strip()

    if not student_id or not password:
        return jsonify({"success": False, "message": "学号和密码不能为空"}), 400

    try:
        student = common.auth.authenticate_student(student_id, password)
    except Exception as exc:
        logger.error("学生认证过程异常: %s", exc)
        return jsonify({"success": False, "message": "登录失败，请稍后重试"}), 500

    if student is None:
        _audit_login_failure(student_id, ip, kind="student")
        return jsonify({"success": False, "message": "学号或密码错误"}), 401

    # 顶号登录：覆盖旧会话并吊销旧 token，不再拒绝第二次登录
    common.auth.supersede_session("student", student["student_id"])
    token = common.auth.generate_student_token(student)
    common.auth.register_session("student", student["student_id"], token)

    return jsonify({
        "success": True,
        "message": "登录成功",
        "data": {
            "token": token,
            "user": {
                "id": student.get("id"),
                "student_id": student.get("student_id"),
                "name": student.get("name"),
                "role": "student",
                "college": student.get("college"),
                "class_name": student.get("class_name"),
            },
        },
    }), 200


@api.route("/student/register", methods=["POST"])
def student_register():
    """学生注册（设置密码）"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效"}), 400

    student_id = (data.get("student_id") or "").strip()
    password = (data.get("password") or "").strip()
    name = (data.get("name") or "").strip()

    if not student_id or not password or not name:
        return jsonify({"success": False, "message": "学号、姓名和密码不能为空"}), 400

    if len(password) < 6:
        return jsonify({"success": False, "message": "密码长度至少6位"}), 400

    ok, msg = _validate_password_strength(password, student_id)
    if not ok:
        return jsonify({"success": False, "message": msg}), 400

    # 检查学生是否存在
    student = common.db.get_student_by_student_id(student_id)
    if student is None:
        return jsonify({"success": False, "message": "学号不存在，请联系辅导员添加"}), 404

    if student.get("password_hash"):
        return jsonify({"success": False, "message": "该学号已注册，请直接登录"}), 400

    # 设置密码
    common.db.set_student_password(student["id"], password)

    # 生成token
    token = common.auth.generate_student_token(student)
    common.auth.register_session("student", student["student_id"], token)

    return jsonify({
        "success": True,
        "message": "注册成功",
        "data": {
            "token": token,
            "user": {
                "id": student.get("id"),
                "student_id": student.get("student_id"),
                "name": student.get("name"),
                "role": "student",
                "college": student.get("college"),
                "class_name": student.get("class_name"),
            },
        },
    }), 200


@api.route("/student/profile", methods=["GET"])
@auth_required
def get_student_profile():
    """获取学生个人信息"""
    if getattr(g, "user_type", "staff") != "student":
        return jsonify({"success": False, "message": "非学生用户"}), 403

    student = common.db.get_student_by_id(g.student_id)
    if student is None:
        return jsonify({"success": False, "message": "学生不存在"}), 404

    return jsonify({
        "success": True,
        "data": student,
    }), 200

@api.route("/auth/profile", methods=["GET"])
@auth_required
@log_action("查看个人信息")
def get_profile():
    """获取当前登录用户的详细信息。"""
    try:
        user = common.auth.get_user(g.user_id)
        if user is None:
            return jsonify({"success": False, "message": "用户不存在"}), 404
        return jsonify({
            "success": True,
            "data": {
                "user_id": user.get("id"),
                "username": user.get("username"),
                "display_name": user.get("display_name"),
                "role": user.get("role"),
                "college": user.get("college"),
                "class_name": user.get("class_name"),
                "email": user.get("email"),
                "phone": user.get("phone"),
                "created_at": user.get("created_at"),
            },
        }), 200
    except Exception as exc:
        logger.error("获取用户信息失败: %s", exc)
        return jsonify({"success": False, "message": "获取用户信息失败"}), 500


@api.route("/auth/profile", methods=["PUT"])
@auth_required
@log_action("更新个人信息")
def update_profile():
    """更新当前用户的个人资料。"""
    data = request.get_json(silent=True)
    if not data:
        return jsonify({"success": False, "message": "请求参数无效，请提供 JSON 数据"}), 400

    allowed_fields = {"name", "email", "phone", "college", "class_name"}
    updates = {k: v for k, v in data.items() if k in allowed_fields and v is not None}

    if not updates:
        return jsonify({"success": False, "message": "没有可更新的字段"}), 400

    try:
        common.auth.update_user(g.user_id, updates)
        return jsonify({"success": True, "message": "个人资料更新成功"}), 200
    except Exception as exc:
        logger.error("更新用户信息失败: %s", exc)
        return jsonify({"success": False, "message": "更新失败，请稍后重试"}), 500
