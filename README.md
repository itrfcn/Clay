# 项目概述

CLAY远程管理系统是一个基于Python和WebSocket技术开发的远程控制工具，允许您通过浏览器界面远程控制多台电脑。

主要功能

- 远程执行终端命令
- 实时输出反馈
- 远程屏幕锁定
- 远程系统关机
- 实时获取屏幕内容
- 远程摄像头监控
- 多客户端管理

版本特色

- 开机自启进程隐藏
- 美观响应式Web控制界面
- 低延迟命令执行和反馈
- 控制端登录页面
- 获取屏幕截图
- 可打包为独立可执行程序
- 心跳机制保证连接稳定

# 运行截图

<img width="1919" height="973" alt="屏幕截图 2025-07-21 201729" src="https://github.com/user-attachments/assets/75d5afca-0a78-4942-b92a-87a1ad8071d9" />
<img width="1919" height="971" alt="屏幕截图 2025-07-21 201828" src="https://github.com/user-attachments/assets/4dd86ad3-4fd0-4e36-a1bd-8cee26d6683e" />
<img width="1918" height="974" alt="屏幕截图 2025-07-21 201849" src="https://github.com/user-attachments/assets/63795f02-49ca-403d-b957-5a17b848a249" />
<img width="1919" height="967" alt="屏幕截图 2025-07-21 201908" src="https://github.com/user-attachments/assets/6550a27d-e1c3-4cb6-84c9-113767612c14" />
<img width="1919" height="969" alt="屏幕截图 2025-07-21 201956" src="https://github.com/user-attachments/assets/82cf0ae6-9c8b-491c-88ed-30ec6993e7e8" />




# 配置教程

### 服务器端配置

服务器端负责接收客户端连接，并提供Web控制界面。配置步骤如下：

**步骤1:** 安装Python环境（推荐Python 3.7+）

**步骤2:** 安装服务器依赖

```
pip install -r server/requirements.txt
```

**步骤3:** 修改服务器配置（可选）

打开 server/app.py 文件，可以根据需要修改以下参数：

- SECRET_KEY - 更改为您自己的安全密钥(第21行)
- PASSWORD - 更改为您自己的登录密码(第118行)
- host - 设置监听地址（默认0.0.0.0表示所有网络接口）
- port - 设置监听端口（默认5000）

### 客户端配置

客户端需要连接到服务器，并执行远程命令。配置步骤如下：

**步骤1:** 安装Python环境（推荐Python 3.7+）

**步骤2:** 安装客户端依赖

```
pip install -r client/requirements.txt
```

**步骤3:** 修改客户端配置

编辑 client/config.py 文件，修改服务器地址：

```
\# 将此地址修改为您的服务器IP地址 SERVER_URL = "http://你的服务器IP:5000"
```





# 运行系统

### 启动服务器

```
cd server python app.py
```

服务器启动后，将在指定端口（默认5000）监听连接。

### 启动客户端

```
cd client python client.py
```

客户端启动后将自动连接到配置文件中指定的服务器地址。

### 访问Web控制界面

打开浏览器，访问：`http://服务器IP:5000`

在Web界面中，可以看到所有连接的客户端，并对其进行管理操作。

# 打包成可执行文件

可以使用PyInstaller将客户端打包成独立的可执行文件（.exe），便于分发和使用：

**步骤1:** 安装PyInstaller

```
pip install pyinstaller
```

**步骤2:** 确保配置文件已正确设置

在打包前，确保client/config.py中的SERVER_URL已设置为正确的服务器地址。

**步骤3:** 执行打包命令

```
cd client pyinstaller --onefile --noconsole --icon=YOURICON.ico client.py
```

注：--noconsole参数会隐藏控制台窗口，如需调试建议移除此参数；YOURICON.ico替换为您自己的图标文件路径

**步骤4:** 获取可执行文件

打包完成后，在dist目录下可以找到client.exe文件，这就是独立的可执行程序。

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

