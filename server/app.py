import time
import platform
import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Any
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room, Namespace
from config import *


# ------------------------------
# 常量定义（避免硬编码，提升可维护性）
# ------------------------------
CLIENT_TYPE_CLIENT = "clay-client"  # 客户端标识
ROOM_WEB_CLIENTS = "web_clients"    # Web管理端房间名
# 事件名称常量
EVENT_SERVER_TIME = "server_time"
EVENT_UPDATE_CLIENT_LIST = "update_client_list"
EVENT_REGISTRATION_SUCCESS = "registration_success"
EVENT_REGISTRATION_FAILED = "registration_failed"


# ------------------------------
# 数据模型（使用dataclass提升类型安全和可读性）
# ------------------------------
@dataclass
class Client:
    """客户端信息数据模型"""
    id: str                  # 客户端唯一标识（SocketIO的sid）
    address: str             # 客户端IP地址
    hostname: str = "未知"    # 主机名
    os: str = "未知"          # 操作系统信息
    last_seen: float = 0.0   # 最后活动时间戳
    connected_at: float = 0.0 # 连接时间戳
    screen_active: bool = False  # 屏幕传输状态
    webcam_active: bool = False  # 摄像头传输状态
    last_screen: float = 0.0     # 最后一次屏幕传输时间戳


# ------------------------------
# 全局状态管理（封装客户端数据操作）
# ------------------------------
class ClientManager:
    """客户端连接管理类，封装客户端数据的增删改查"""
    def __init__(self):
        self.clients: Dict[str, Client] = {}  # client_id -> Client

    def add_client(self, client_id: str, address: str) -> None:
        """添加新客户端"""
        timestamp = time.time()
        self.clients[client_id] = Client(
            id=client_id,
            address=address,
            last_seen=timestamp,
            connected_at=timestamp
        )
        logger.debug(f"客户端已添加: {client_id}")

    def remove_client(self, client_id: str) -> None:
        """移除客户端"""
        if client_id in self.clients:
            del self.clients[client_id]
            logger.debug(f"客户端已移除: {client_id}")

    def update_client_info(self, client_id: str, hostname: str, os_info: str) -> bool:
        """更新客户端基本信息（主机名、操作系统）"""
        client = self.get_client(client_id)
        if not client:
            return False
        client.hostname = hostname
        client.os = os_info
        client.last_seen = time.time()
        return True

    def update_last_seen(self, client_id: str) -> bool:
        """更新客户端最后活动时间"""
        client = self.get_client(client_id)
        if not client:
            return False
        client.last_seen = time.time()
        return True

    def update_media_status(self, client_id: str, media_type: str, status: bool) -> bool:
        """更新客户端媒体传输状态（屏幕/摄像头）"""
        client = self.get_client(client_id)
        if not client:
            return False
        if media_type == "screen":
            client.screen_active = status
            if status:
                client.last_screen = time.time()
        elif media_type == "webcam":
            client.webcam_active = status
        return True

    def get_client(self, client_id: str) -> Optional[Client]:
        """获取单个客户端信息"""
        return self.clients.get(client_id)

    def get_all_clients(self) -> List[Dict[str, Any]]:
        """获取所有客户端列表（转换为字典用于JSON序列化）"""
        return [client.__dict__ for client in self.clients.values()]

    def get_timeout_clients(self, now: float, timeout_threshold: int, media_multiplier: int) -> List[str]:
        """获取超时客户端ID列表"""
        timeout_ids = []
        for client_id, client in self.clients.items():
            # 基础超时判断
            if now - client.last_seen > timeout_threshold:
                # 媒体传输中延长超时
                if (client.screen_active or client.webcam_active):
                    if now - client.last_seen > timeout_threshold * media_multiplier:
                        timeout_ids.append(client_id)
                else:
                    timeout_ids.append(client_id)
        return timeout_ids


# ------------------------------
# 初始化组件
# ------------------------------
# 初始化Flask应用
app = Flask(__name__)
app.config.update(
    SECRET_KEY=SECRET_KEY,
    JSON_SORT_KEYS=JSON_SORT_KEYS,
    MAX_CONTENT_LENGTH=MAX_CONTENT_LENGTH
)

# 初始化SocketIO
socketio = SocketIO(
    app,
    async_mode=SOCKETIO_ASYNC_MODE,
    cors_allowed_origins=SOCKETIO_CORS_ALLOWED_ORIGINS,
    ping_timeout=SOCKETIO_PING_TIMEOUT,
    ping_interval=SOCKETIO_PING_INTERVAL,
    max_http_buffer_size=SOCKETIO_MAX_HTTP_BUFFER_SIZE
)

# 初始化客户端管理器
client_manager = ClientManager()

# 配置日志
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL),
    format=LOG_FORMAT,
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)


# ------------------------------
# Flask路由
# ------------------------------
@app.route("/", methods=["GET", "POST"])
def index() -> str:
    """管理后台登录与主页"""
    if request.method == "POST":
        password = request.form.get("password", "")
        if password == ADMIN_PASSWORD:
            return render_template("index.html")
        return render_template("login.html", error="密码错误")
    return render_template("login.html")


@app.route("/api/clients", methods=["GET"])
def api_get_clients() -> jsonify:
    """API接口：获取客户端列表"""
    return jsonify({
        "success": True,
        "clients": client_manager.get_all_clients()
    })


# ------------------------------
# SocketIO事件处理（使用类封装，结构更清晰）
# ------------------------------
class MainNamespace(Namespace):
    """主命名空间，集中处理所有SocketIO事件"""

    def on_connect(self) -> None:
        """处理新连接"""
        client_id = request.sid
        client_address = request.remote_addr
        client_type = request.headers.get("Client-Type", "")

        try:
            if client_type == CLIENT_TYPE_CLIENT:
                # 客户端连接处理
                logger.info(f"客户端连接: ID={client_id}, IP={client_address}")
                client_manager.add_client(client_id, client_address)
                self._broadcast_client_list()  # 广播客户端列表更新
                # 发送服务器时间同步
                emit(EVENT_SERVER_TIME, {"timestamp": time.time()}, room=client_id)
            else:
                # Web管理端连接处理
                logger.info(f"Web界面连接: ID={client_id}, IP={client_address}")
                join_room(ROOM_WEB_CLIENTS)
                # 发送当前客户端列表
                emit(EVENT_UPDATE_CLIENT_LIST, client_manager.get_all_clients(), room=client_id)

        except Exception as e:
            logger.error(f"连接处理错误: {str(e)}", exc_info=True)  # 记录堆栈信息，便于调试
            emit("connection_error", {"message": str(e)}, room=client_id)

    def on_disconnect(self) -> None:
        """处理断开连接"""
        client_id = request.sid
        client = client_manager.get_client(client_id)

        try:
            if client:
                logger.info(f"客户端断开连接: ID={client_id}, 主机名={client.hostname}")
                client_manager.remove_client(client_id)
                self._broadcast_client_list()
            else:
                logger.warning(f"未知客户端断开连接: ID={client_id}")

        except Exception as e:
            logger.error(f"断开连接处理错误: {str(e)}", exc_info=True)

    def on_register(self, data: Dict[str, str]) -> None:
        """处理客户端注册信息（主机名、操作系统）"""
        client_id = request.sid
        hostname = data.get("hostname", "未知")
        os_info = data.get("os", "未知")

        try:
            if not client_manager.get_client(client_id):
                logger.warning(f"无效注册尝试: 客户端 {client_id} 未连接")
                emit(EVENT_REGISTRATION_FAILED, {"message": "无效的客户端连接"}, room=client_id)
                return

            # 更新客户端信息
            client_manager.update_client_info(client_id, hostname, os_info)
            logger.info(f"客户端注册完成: ID={client_id}, 主机名={hostname}, 操作系统={os_info}")
            self._broadcast_client_list()
            emit(EVENT_REGISTRATION_SUCCESS, {"message": "注册成功"}, room=client_id)

        except Exception as e:
            logger.error(f"注册处理错误: {str(e)}", exc_info=True)
            emit(EVENT_REGISTRATION_FAILED, {"message": str(e)}, room=client_id)

    def on_heartbeat(self, data: Dict[str, Any]) -> None:
        """处理客户端心跳（维持连接）"""
        client_id = request.sid
        try:
            if client_manager.get_client(client_id):
                client_manager.update_last_seen(client_id)
                # 每5秒回应一次心跳
                if time.time() % 5 < 1:
                    emit("heartbeat_ack", {"timestamp": time.time()}, room=client_id)
            else:
                logger.warning(f"未知客户端心跳: ID={client_id}, 请求重新注册")
                emit("request_register", {"reason": "客户端未注册"}, room=client_id)

        except Exception as e:
            logger.error(f"心跳处理错误: {str(e)}", exc_info=True)

    def on_terminal_output(self, data: Dict[str, str]) -> None:
        """处理终端输出并转发给Web管理端"""
        client_id = request.sid
        output = data.get("output", "")

        try:
            if not output:
                logger.warning(f"空终端输出来自 {client_id}")
                return

            logger.info(f"终端输出来自 {client_id}: {output.strip()[:100]}...")
            # 转发给所有Web客户端
            emit("terminal_output", {
                "client_id": client_id,
                "output": output,
                "timestamp": time.time()
            }, room=ROOM_WEB_CLIENTS)

        except Exception as e:
            logger.error(f"终端输出处理错误: {str(e)}", exc_info=True)

    def on_webcam_frame(self, data: Dict[str, str]) -> None:
        """处理摄像头帧数据并转发"""
        client_id = request.sid
        image_data = data.get("image_data", "")

        try:
            if not image_data:
                logger.warning(f"空摄像头数据来自 {client_id}")
                return

            client_manager.update_media_status(client_id, "webcam", True)
            logger.info(f"摄像头数据来自 {client_id} (长度: {len(image_data)})")
            emit("webcam_frame", {
                "client_id": client_id,
                "image_data": image_data,
                "timestamp": data.get("timestamp", time.time())
            }, room=ROOM_WEB_CLIENTS)

        except Exception as e:
            logger.error(f"摄像头数据处理错误: {str(e)}", exc_info=True)
            client_manager.update_media_status(client_id, "webcam", False)

    def on_screen_frame(self, data: Dict[str, Any]) -> None:
        """处理屏幕截图帧数据并转发"""
        client_id = request.sid
        image_data = data.get("image_data", "")

        try:
            if not image_data:
                logger.warning(f"空屏幕数据来自 {client_id}")
                return

            client_manager.update_media_status(client_id, "screen", True)
            logger.info(f"屏幕数据来自 {client_id} (长度: {len(image_data)})")
            emit("screen_frame", {
                "client_id": client_id,
                "image_data": image_data,
                "timestamp": data.get("timestamp", time.time()),
                "width": data.get("width"),
                "height": data.get("height")
            }, room=ROOM_WEB_CLIENTS)

        except Exception as e:
            logger.error(f"屏幕数据处理错误: {str(e)}", exc_info=True)
            client_manager.update_media_status(client_id, "screen", False)

    def on_execute_command(self, data: Dict[str, str]) -> None:
        """处理Web端的命令执行请求"""
        target_client_id = data.get("client_id")
        command = data.get("command", "")
        sender_id = request.sid  # 记录发送者ID

        try:
            if not target_client_id:
                error_msg = "未指定目标客户端ID"
                logger.error(f"命令执行错误: {error_msg} (发送者: {sender_id})")
                emit("command_error", {"message": error_msg}, room=sender_id)
                return

            if not client_manager.get_client(target_client_id):
                error_msg = f"客户端 {target_client_id} 不存在或已断开"
                logger.error(f"命令执行错误: {error_msg} (发送者: {sender_id})")
                emit("command_error", {"message": error_msg}, room=sender_id)
                return

            logger.info(f"命令发送到 {target_client_id}: {command} (发送者: {sender_id})")
            # 发送命令到目标客户端
            emit("execute_command", {
                "command": command,
                "sender": sender_id
            }, room=target_client_id)
            # 向发送者确认命令已发送
            emit("command_sent", {
                "client_id": target_client_id,
                "command": command,
                "timestamp": time.time()
            }, room=sender_id)

        except Exception as e:
            logger.error(f"命令执行请求处理错误: {str(e)}", exc_info=True)
            emit("command_error", {"message": str(e)}, room=sender_id)

    # 其他事件处理方法（on_command_result, on_interrupt_command等）保持类似优化逻辑...

    def _broadcast_client_list(self) -> None:
        """广播客户端列表更新到所有Web管理端"""
        try:
            socketio.emit(
                EVENT_UPDATE_CLIENT_LIST,
                client_manager.get_all_clients(),
                room=ROOM_WEB_CLIENTS
            )
            logger.debug("客户端列表已广播更新")
        except Exception as e:
            logger.error(f"客户端列表广播错误: {str(e)}", exc_info=True)


# 注册命名空间
socketio.on_namespace(MainNamespace("/"))


# ------------------------------
# 后台任务（客户端超时检查）
# ------------------------------
def check_client_timeouts() -> None:
    """客户端超时检查后台任务"""
    logger.info("客户端超时检查任务已启动")
    while True:
        try:
            now = time.time()
            timeout_threshold = CLIENT_TIMEOUT_SECONDS
            media_multiplier = CLIENT_MEDIA_TIMEOUT_MULTIPLIER
            # 获取超时客户端ID
            timeout_ids = client_manager.get_timeout_clients(now, timeout_threshold, media_multiplier)

            # 处理超时客户端
            for client_id in timeout_ids:
                client = client_manager.get_client(client_id)
                if client:
                    logger.warning(f"客户端超时断开: {client_id} ({client.hostname})")
                    client_manager.remove_client(client_id)
            if timeout_ids:
                MainNamespace("/")._broadcast_client_list()  # 广播更新

        except Exception as e:
            logger.error(f"超时检查任务错误: {str(e)}", exc_info=True)

        # 等待检查间隔
        socketio.sleep(CLIENT_TIMEOUT_CHECK_INTERVAL)


# ------------------------------
# 启动服务器
# ------------------------------
if __name__ == "__main__":
    # 启动超时检查后台任务
    socketio.start_background_task(check_client_timeouts)

    logger.info("Clay 远程管理服务器启动中...")
    logger.info(f"系统信息: {platform.system()} {platform.release()}")

    try:
        socketio.run(
            app,
            host=SERVER_HOST,
            port=SERVER_PORT,
            debug=DEBUG_MODE,
            allow_unsafe_werkzeug=ALLOW_UNSAFE_WERKZEUG
        )
    except Exception as e:
        logger.critical(f"服务器启动失败: {str(e)}", exc_info=True)
        exit(1)