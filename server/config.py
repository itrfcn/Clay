# 服务器基本配置
SERVER_HOST = '0.0.0.0'
SERVER_PORT = 5000
DEBUG_MODE = True
ALLOW_UNSAFE_WERKZEUG = True  # 开发环境使用

# Flask应用配置
SECRET_KEY = 'your_very_secret_key_here!'  # 生产环境建议使用环境变量
JSON_SORT_KEYS = False  # 保持JSON字段顺序
MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 限制上传大小为16MB

# SocketIO配置
SOCKETIO_ASYNC_MODE = "eventlet"
SOCKETIO_PING_TIMEOUT = 60
SOCKETIO_PING_INTERVAL = 10
SOCKETIO_MAX_HTTP_BUFFER_SIZE = 16 * 1024 * 1024  # 支持大尺寸图像传输
SOCKETIO_CORS_ALLOWED_ORIGINS = "*"  # 开发环境允许跨域，生产环境需限制

# 认证配置
ADMIN_PASSWORD = 'admin123'  # 生产环境使用环境变量

# 客户端超时配置
CLIENT_TIMEOUT_SECONDS = 60  # 基础超时时间（秒）
CLIENT_MEDIA_TIMEOUT_MULTIPLIER = 3  # 媒体传输时超时时间倍数
CLIENT_TIMEOUT_CHECK_INTERVAL = 30  # 超时检查间隔（秒）

# 日志配置
LOG_LEVEL = 'INFO'
LOG_FORMAT = '%(asctime)s - %(levelname)s - %(message)s'
LOG_FILE = 'server.log'