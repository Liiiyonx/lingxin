import os
import sys
import logging

ROOT_DIR = os.path.dirname(os.path.abspath(__file__))
if ROOT_DIR not in sys.path:
    sys.path.insert(0, ROOT_DIR)

from flask import Flask, send_from_directory, jsonify, send_file, request, Response
from flask_cors import CORS
from flask_socketio import SocketIO, emit, join_room, leave_room
from config.config import ApplicationConfig, load_config
from api.routes import api, set_socketio

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("campus_mind")


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

    CORS(app, resources={r"/api/*": {"origins": ["http://localhost:5000", "http://127.0.0.1:5000"]}})

    # 初始化WebSocket
    socketio = SocketIO(app, cors_allowed_origins=["http://localhost:5000", "http://127.0.0.1:5000"], async_mode='threading')

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

    @socketio.on('send_message')
    def handle_message(data):
        room = data.get('room')
        message = data.get('message')
        if room and message:
            emit('new_message', message, room=room)
            logger.info(f'Message sent to room: {room}')

    # --- WebRTC 视频通话信令 ---
    @socketio.on('video_call_request')
    def handle_video_call_request(data):
        """学生发起视频呼叫 → 广播给所有老师端（含房间号）"""
        room = data.get('room', 'video_room')
        join_room(room)
        emit('incoming_video_call', data, broadcast=True)
        logger.info(f"视频呼叫请求: 学生 {data.get('student_name')} room={room}")

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
        logger.info('Database initialized')
    except Exception as e:
        logger.warning(f"Database init skipped: {e}")

    @app.route("/")
    def index():
        index_path = os.path.join(app.template_folder, "index.html")
        if os.path.exists(index_path):
            with open(index_path, "rb") as f:
                html_bytes = f.read()
            resp = Response(html_bytes, content_type="text/html; charset=utf-8")
            resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
            resp.headers["Pragma"] = "no-cache"
            resp.headers["Expires"] = "0"
            return resp
        return jsonify({
            "name": ApplicationConfig.APP_NAME,
            "version": ApplicationConfig.VERSION,
            "status": "running",
            "message": "Backend running, visit /api for docs."
        })

    @app.route("/favicon.ico")
    def favicon():
        return "", 204

    @app.route("/system/info")
    def system_info():
        return jsonify({
            "name": ApplicationConfig.APP_NAME,
            "version": ApplicationConfig.VERSION,
            "endpoints": {
                "auth": "/api/auth/login",
                "conversations": "/api/conversation/list",
                "emotion": "/api/emotion/logs",
                "alerts": "/api/alert/list",
                "knowledge": "/api/knowledge/stats",
                "dashboard": "/api/system/dashboard",
            }
        })

    @app.errorhandler(404)
    def not_found(e):
        if request.path.startswith("/api/") or request.path.startswith("/static/") or request.path.startswith("/socket.io"):
            return jsonify({"error": "Not found", "code": 404}), 404
        # 只对浏览器页面请求返回 index.html
        accept = request.headers.get("Accept", "")
        if "text/html" in accept:
            index_path = os.path.join(app.template_folder, "index.html")
            try:
                with open(index_path, "rb") as f:
                    html_bytes = f.read()
                return Response(html_bytes, content_type="text/html; charset=utf-8")
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


if __name__ == "__main__":
    app = create_app()
    print_banner(app)
    app.socketio.run(
        app,
        host=ApplicationConfig.HOST,
        port=ApplicationConfig.PORT,
        debug=ApplicationConfig.DEBUG
    )
