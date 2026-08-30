import os
import sys
import logging
import re

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from flask import Flask, send_from_directory, jsonify, send_file, request, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from config.config import AgoraConfig, ApplicationConfig, load_config
from config.agora_token import Role_Publisher, build_token_with_user_account
from api.routes import api, set_socketio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("campus_mind")


def _allowed_origins():
    port = ApplicationConfig.PORT
    raw = os.getenv(
        "ALLOWED_ORIGINS",
        f"http://localhost:{port},http://127.0.0.1:{port}"
    )
    origins = [o.strip() for o in raw.split(",") if o.strip()]
    # 当前主机端口永远放行，方便本地换端口调试，也避免 .env 固定端口导致 WebSocket 被拒
    for local in (f"http://localhost:{port}", f"http://127.0.0.1:{port}"):
        if local not in origins:
            origins.append(local)
    return origins


def create_app():
    app = Flask(
        __name__,
        static_folder=os.path.join(ROOT_DIR, "static"),
        template_folder=os.path.join(ROOT_DIR, "templates")
    )

    # SECRET_KEY 安全校验：生产环境必须设置，开发环境使用固定回退
    secret = ApplicationConfig.SECRET_KEY
    if not secret:
        if ApplicationConfig.DEBUG:
            secret = "lingxin-dev-secret-key-change-in-production"
            logger.warning("⚠ SECRET_KEY 未设置，使用开发模式默认值（生产环境请务必设置！）")
        else:
            raise RuntimeError("FATAL: SECRET_KEY 环境变量未设置！生产环境必须设置强随机密钥。")
    app.config["SECRET_KEY"] = secret
    app.config["MAX_CONTENT_LENGTH"] = 100 * 1024 * 1024
    app.config["JSON_AS_ASCII"] = False

    allowed_origins = _allowed_origins()
    CORS(app, resources={r"/api/*": {"origins": allowed_origins}})

    # 初始化WebSocket
    socketio = SocketIO(app, cors_allowed_origins=allowed_origins, async_mode='threading')

    app.register_blueprint(api)

    from api.routes import init_services
    init_services(app)

    # WebSocket事件处理
    @socketio.on('connect')
    def handle_connect():
        logger.info('WebSocket connected')

    @socketio.on('disconnect')
    def handle_disconnect():
        logger.info('WebSocket disconnected')

    @socketio.on('join')
    def handle_join(data):
        room = data.get('room')
        if room:
            join_room(room)
            logger.info(f'User joined room: {room}')

    @socketio.on('leave')
    def handle_leave(data):
        room = data.get('room')
        if room:
            leave_room(room)
            logger.info(f'User left room: {room}')

    # --- WebRTC 视频通话信令 ---
    @socketio.on('video_call_request')
    def handle_video_call_request(data):
        """视频呼叫请求：学生→定向推送指定辅导员，其余→广播（含房间号）"""
        room = data.get('room', 'video_room')
        join_room(room)
        counselor_id = data.get('counselor_id')
        if data.get('caller') == 'student' and counselor_id:
            # 学生呼叫定向到指定辅导员（teacher_chat_{user_id} 房间）
            target_room = 'teacher_chat_' + str(counselor_id)
            emit('incoming_video_call', data, room=target_room)
            logger.info(f"视频呼叫请求: 学生 {data.get('student_name')} → 辅导员{counselor_id} room={room}")
        else:
            emit('incoming_video_call', data, broadcast=True)
            logger.info(f"视频呼叫请求: {data.get('caller')} room={room}")

    @socketio.on('video_call_accept')
    def handle_video_call_accept(data):
        """老师接受视频呼叫"""
        room = data.get('room', 'video_room')
        join_room(room)
        emit('video_call_accepted', data, room=room)
        logger.info(f"视频通话已接受: room={room}")

    @socketio.on('video_offer')
    def handle_video_offer(data):
        """转发 WebRTC Offer"""
        room = data.get('room', 'video_room')
        emit('video_offer', data, room=room)

    @socketio.on('video_answer')
    def handle_video_answer(data):
        """转发 WebRTC Answer"""
        room = data.get('room', 'video_room')
        emit('video_answer', data, room=room)

    @socketio.on('video_ice_candidate')
    def handle_video_ice(data):
        """转发 ICE Candidate"""
        room = data.get('room', 'video_room')
        emit('video_ice_candidate', data, room=room)

    @socketio.on('video_call_end')
    def handle_video_call_end(data):
        """结束视频通话"""
        room = data.get('room', 'video_room')
        emit('video_call_ended', data, room=room)
        logger.info(f"视频通话结束: room={room}")

    app.socketio = socketio
    set_socketio(socketio)

    try:
        from core.database import DatabaseManager
        db_manager = DatabaseManager()
        db_manager.init_db()
        db_manager.migrate_student_id_links()
        db_manager.migrate_core_columns()
        logger.info('Database initialized')
    except Exception as e:
        logger.warning(f"Database init skipped: {e}")

    def render_index_html():
        index_path = os.path.join(app.template_folder, "index.html")
        with open(index_path, encoding="utf-8") as f:
            html = f.read()

        partial_dir = os.path.abspath(os.path.join(app.template_folder, "partials"))
        include_re = re.compile(r"<!-- INCLUDE:partials/([A-Za-z0-9_\-]+\.html) -->")

        def include_file(match):
            name = match.group(1)
            partial_path = os.path.abspath(os.path.join(partial_dir, name))
            if not partial_path.startswith(partial_dir + os.sep):
                logger.warning("Blocked unsafe partial include: %s", name)
                return match.group(0)
            try:
                with open(partial_path, encoding="utf-8") as pf:
                    return pf.read()
            except FileNotFoundError:
                logger.warning("Missing partial template: %s", name)
                return match.group(0)

        return include_re.sub(include_file, html)

    @app.route("/")
    def index():
        html = render_index_html()
        resp = Response(html.encode("utf-8"), content_type="text/html; charset=utf-8")
        resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        resp.headers["Pragma"] = "no-cache"
        resp.headers["Expires"] = "0"
        return resp

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.route("/system/info")
    def system_info():
        return jsonify({
            "name": ApplicationConfig.APP_NAME,
            "version": ApplicationConfig.VERSION,
            "video": {
                "agora": {
                    "app_id": AgoraConfig.APP_ID,
                    "token": AgoraConfig.TOKEN or None,
                }
            },
            "endpoints": {
                "auth": "/api/auth/login",
                "conversations": "/api/conversation/list",
                "emotion": "/api/emotion/logs",
                "alerts": "/api/alert/list",
                "knowledge": "/api/knowledge/stats",
                "dashboard": "/api/system/dashboard",
            }
        })

    @app.route("/api/video/agora-token")
    def agora_token():
        channel = (request.args.get("channel") or "").strip()
        uid = (request.args.get("uid") or "").strip()
        if not channel or not uid or len(channel.encode("utf-8")) > 64:
            return jsonify({"error": "channel and uid are required", "code": 400}), 400
        if AgoraConfig.TOKEN:
            # 控制台临时 Token：优先于无鉴权，直接复用同一把 token
            return jsonify({"token": AgoraConfig.TOKEN, "mode": "static_token"})
        if not AgoraConfig.APP_CERT:
            return jsonify({"token": None, "mode": "no_auth"})
        expire_seconds = AgoraConfig.TOKEN_EXPIRE_HOURS * 3600
        token = build_token_with_user_account(
            AgoraConfig.APP_ID,
            AgoraConfig.APP_CERT,
            channel,
            uid,
            Role_Publisher,
            expire_seconds,
        )
        return jsonify({"token": token, "mode": "app_cert", "expires_in": expire_seconds})

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/") or request.path.startswith("/static/") or request.path.startswith("/socket.io"):
            return jsonify({"error": "Not found", "code": 404}), 404
        # 只对浏览器页面请求返回 index.html
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            try:
                html = render_index_html()
                return Response(html.encode("utf-8"), content_type="text/html; charset=utf-8")
            except FileNotFoundError:
                return jsonify({"error": "Page not found", "code": 404}), 404
        return jsonify({"error": "Not found", "code": 404}), 404

    @app.errorhandler(500)
    def server_error(e):
        return jsonify({"error": "Internal server error", "code": 500}), 500

    @app.errorhandler(413)
    def too_large(e):
        return jsonify({"error": "File too large (max 100MB)", "code": 413}), 413

    return app


def print_banner(app):
    cfg = load_config()
    print()
    print("=" * 60)
    print(f"  {cfg['app'].APP_NAME} v{cfg['app'].VERSION}")
    print("=" * 60)
    print(f"  >> http://{cfg['app'].HOST}:{cfg['app'].PORT}")
    print(f"  >> Database: {cfg['app'].DATABASE_URI}")
    print(f"  >> Model: {cfg['llm'].DEFAULT_MODEL}")
    print(f"  >> API Key: {'[OK] Configured' if cfg['llm'].DASHSCOPE_API_KEY else '[X] Not configured'}")
    print(f"  >> Debug: {'ON' if cfg['app'].DEBUG else 'OFF'}")
    print("=" * 60)
    print()


# 模块级应用实例：供 gunicorn（systemd 生产部署）导入使用
app = create_app()


if __name__ == "__main__":
    print_banner(app)
    app.socketio.run(
        app,
        host=ApplicationConfig.HOST,
        port=ApplicationConfig.PORT,
        debug=ApplicationConfig.DEBUG
    )
