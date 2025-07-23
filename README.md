# 🔐 CLAY 远程管理系统：跨平台设备集中控制解决方案

CLAY 远程管理系统是一款基于 Python 与 WebSocket 技术栈开发的轻量级远程控制工具，旨在通过浏览器界面实现对多台不同平台的设备进行集中化管理。无论是个人设备远程维护、小型办公网络管控，还是跨地域设备监控，CLAY 都能提供稳定、高效的解决方案。

官网 [CLAY 远程管理系统 ](https://itrf.cn/clay)

开源地址[CLAY 远程管理系统：跨平台设备集中控制解决方案](https://github.com/itrfcn/Clay)

## ✨ 功能亮点



### 基础控制能力

- **📋 交互式终端**：支持所有系统原生命令，实时输出执行结果，保留完整命令历史
- **⚡ 低延迟响应**：基于 WebSocket 全双工通信，命令执行与反馈几乎无感知延迟
- **📂 目录导航**：支持 `cd` 命令切换工作目录，自动显示目录内容，操作体验与本地终端一致

### 设备监控功能

- **🖥️ 屏幕捕获**：实时获取设备屏幕内容，支持画质（0-100%）与刷新频率调节，平衡清晰度与带宽占用
- **📹 摄像头访问**：远程调用设备摄像头，一键捕获实时画面，支持应急监控场景
- **📊 系统信息**：实时展示 CPU 使用率、内存占用、磁盘空间、网络流量等硬件状态

### 设备管理特性

- **🔗 多客户端支持**：服务器可同时管理数十台设备，通过设备名称快速区分与切换
- **🔄 自动重连**：网络中断后自动尝试重连，恢复连接后无缝继续控制
- **🚀 开机自启**：客户端支持开机自动运行，设备重启后无需手动干预即可重新上线
- **🕵️ 进程隐藏**：客户端可隐藏运行窗口与进程名称，适合无人值守场景

## 🎨 界面预览

| 功能场景     | 界面截图                                                     |
| ------------ | ------------------------------------------------------------ |
| **登录验证** | <img width="1920" height="975" alt="登录验证" src="https://github.com/user-attachments/assets/04840176-db0d-4d67-952e-997b10408aa7" />|
| **设备列表** | <img width="1920" height="975" alt="设备列表" src="https://github.com/user-attachments/assets/dd5636ea-e08e-4cbc-b8de-d8ea53f77d0c" />|
| **终端控制** | <img width="1920" height="975" alt="终端控制" src="https://github.com/user-attachments/assets/57d999c1-02d2-4aa3-a9a1-105dcd668c68" />|
| **内置指令** | <img width="1920" height="975" alt="内置指令" src="https://github.com/user-attachments/assets/d0bc475f-c7cc-44c5-a0d8-87b575ad510e" />|
| **媒体监控** | <img width="1920" height="975" alt="媒体监控" src="https://github.com/user-attachments/assets/5414cb1e-ae82-460b-93e0-2226f8afee6a" />|

##🛠️ 详细部署指南

### 服务器端部署

#### 环境要求

- 操作系统：Windows 10/11、Linux（Ubuntu 18.04+、CentOS 7+）、macOS 10.15+
- Python 版本：3.7 及以上
- 网络：确保服务器端口（默认 5000）可被客户端访问

#### 安装步骤

1. **获取源码**
   克隆仓库或下载源码包，解压后进入项目目录。

2. **安装依赖**

   ```bash
   # 进入服务器目录
   cd server
   # 安装依赖包
   pip install -r requirements.txt
   ```

3. **配置服务器参数**
   编辑 `server/config.py` 文件，根据实际需求修改核心配置：

   ```python
   # 核心配置：安全密钥登录密码（必填）
   SECRET_KEY # 更改为您自己的安全密钥
   ADMIN_PASSWORD # 更改为您自己的登录密码
   
   # 可选配置：根据网络环境调整
   SERVER_HOST # 设置监听地址（默认0.0.0.0表示所有网络接口）
   SERVER_PORT # 设置监听端口（默认5000）
   ```

### 客户端部署

#### 环境要求

- 支持系统：Windows 7+、Linux（Ubuntu/Debian/CentOS）、macOS 10.13+
- Python 版本：3.7 及以上（打包后可脱离 Python 环境运行）

#### 安装步骤

1. **安装依赖**

   ```bash
   # 进入客户端目录
   cd client
   # 安装依赖包
   pip install -r requirements.txt
   ```

2. **配置服务器连接**
   编辑 `client/config.py` 文件，设置服务器地址：

   ```python
   # 核心配置：服务器地址（必填）
   SERVER_URL = "http://your_server_ip:5000"  # 替换为实际服务器IP和端口
   
   # 可选配置：根据网络环境调整
   HEARTBEAT_INTERVAL = 30  # 心跳包发送间隔（秒）
   RECONNECT_DELAY = 10     # 断线重连间隔（秒）
   SCREENSHOT_INTERVAL = 2  # 屏幕截图刷新间隔（秒）
   ```

3. **功能开关配置**
   可根据需求开启 / 关闭以下功能：

   ```python
   HIDE_PROCESS = True  # 隐藏进程窗口（默认开启）
   ```

## 🚀 系统运行指南

### 启动服务器

```bash
cd server
# Windows 系统
python app.py
# Linux/macOS 系统
python3 app.py
```

启动成功后，终端将显示：`Running on http://0.0.0.0:5000/ (Press CTRL+C to quit)`

### 启动客户端

```bash
cd client
# Windows 系统
python client.py
# Linux/macOS 系统
python3 client.py
```

客户端启动后无界面（默认隐藏），可通过服务器 Web 界面确认连接状态。

### 访问控制界面

1. 打开浏览器，访问 `http://服务器IP:5000`（替换为实际服务器地址）
2. 输入 `server/app.py` 中配置的 `ADMIN_PASSWORD` 登录
3. 在「设备列表」中选择已连接的客户端，即可进行远程操作

## 📦 客户端打包为可执行文件

为简化在无 Python 环境设备上的部署，可将客户端打包为系统原生可执行文件：

### 打包步骤

1. **安装打包工具**

   ```bash
   pip install pyinstaller
   ```

2. **执行打包命令**

   ```bash
   cd client
   
   # Windows 平台（生成 .exe 文件）
   pyinstaller --onefile --noconsole --icon=icon.ico client.py
   
   # Linux 平台（生成可执行文件）
   pyinstaller --onefile --noconsole --icon=icon.png client.py
   
   # macOS 平台（生成 .app 应用）
   pyinstaller --onefile --noconsole --icon=icon.icns client.py
   ```

   - `--onefile`：打包为单个文件
   - `--noconsole`：隐藏控制台窗口（调试时可移除）
   - `--icon`：指定程序图标（可选）

3. **获取打包产物**
   打包完成后，可在 `client/dist` 目录下找到生成的可执行文件（如 `client.exe`），直接复制到目标设备运行即可。

## 🔒 安全加固建议

### 基础安全措施

1. **修改默认密码**：务必替换 `server/config.py` 中的 `SECRET_KEY` 和 `ADMIN_PASSWORD`，避免使用弱密码
2. **限制网络访问**：通过防火墙仅开放服务器端口给信任的 IP 地址
3. **定期更新**：及时更新客户端和服务器代码，修复潜在安全漏洞

## ❓ 常见问题解决

1. **客户端无法连接服务器**
   - 检查 `SERVER_URL` 是否正确（IP、端口是否可达）
   - 确认服务器已启动且防火墙未拦截端口
   - 测试网络连通性：`ping 服务器IP` + `telnet 服务器IP 端口`
2. **屏幕截图 / 摄像头无画面**
   - Windows：检查设备是否开启「屏幕捕获权限」「摄像头权限」
   - Linux：确保当前用户有 `sudo` 权限（部分桌面环境需要）
   - macOS：在「系统设置 - 安全性与隐私」中授予终端 / 应用访问权限
3. **打包后无法运行**
   - 确保打包时已关闭杀毒软件（可能误删文件）
   - 检查 `config.py` 中服务器地址是否正确（打包后无法修改）
   - 尝试移除 `--noconsole` 参数，查看运行时错误信息

# 安全注意事项

> [!WARNING]
>
>
> 此系统具有强大的远程控制功能，请注意以下安全事项：
>
> 1. 仅在授权的环境中使用
> 2. 确保服务器端口不对外开放或使用防火墙限制访问
> 3. 为服务器启用HTTPS加密（生产环境必须）
> 4. 更改默认配置，特别是安全密钥
> 5. 实现适当的身份验证机制（建议添加）
>
> 未经授权使用此系统可能违反法律法规。

