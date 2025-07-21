# 客户端配置文件

# !!! 重要：修改为你的 Flask 服务器的实际 IP 地址和端口 !!!
# 如果服务器和客户端在同一台机器上测试，可以使用 'http://127.0.0.1:5000'
# 如果在局域网内，使用服务器的局域网 IP，例如 'http://192.168.1.100:5000'
# 如果服务器有公网 IP 或域名，使用公网地址
SERVER_URL = "http://localhost:5000"

# 心跳间隔（秒）
HEARTBEAT_INTERVAL = 30

# 重新连接尝试间隔（秒）
RECONNECT_DELAY = 5

SCREENSHOT_INTERVAL = 30