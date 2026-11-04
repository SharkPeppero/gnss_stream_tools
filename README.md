# GNSS Raw Stream

用于测试 GNSS 接收机与 NTRIP 差分服务的 Python 工具。它可以：

- 连接 NTRIP caster，发送 GGA 请求并解析 RTCM 数据流；
- 通过 GUI 打开 GNSS 串口，查看 NMEA、RTCM、定位质量和数据统计；
- 将 RTCM 数据转发写入接收机串口；
- 保存原始串口数据，便于后续分析。

## 目录说明

- `gnss_raw_stream.py`: 程序入口，支持命令行 NTRIP 测试和 GUI 模式。
- `gui.py`: 图形界面。
- `serial_worker.py`: 串口读写与 RTCM 转发。
- `ntrip_client.py`、`ntrip_worker.py`: NTRIP 连接与数据读取。
- `nmea.py`、`rtcm.py`、`raw_stream.py`: NMEA/RTCM 解析及原始流分析。
- `config.py`: 默认 NTRIP 和 GGA 配置。

## 运行环境

Python 3.8 或更高版本。GUI 和串口功能需要安装：

```bash
python3 -m pip install PyQt5 pyserial PyYAML
```

有些 Linux 发行版中，普通用户还需要加入串口用户组后重新登录：

```bash
sudo usermod -aG dialout "$USER"
```

## 启动方式

进入工具目录：

```bash
cd /path/to/gnss_raw_stream
```

启动图形界面：

```bash
python3 gnss_raw_stream.py
```

或明确指定 GUI 模式：

```bash
python3 gnss_raw_stream.py --gui
```

查看命令行参数：

```bash
python3 gnss_raw_stream.py --help
```

## 命令行 NTRIP 测试

以下示例连接 NTRIP 服务 60 秒，并使用给定坐标构造 GGA：

```bash
python3 gnss_raw_stream.py \
  --host pnt.true-point.com \
  --port 8002 \
  --mountpoint RTCM33GRCEJ \
  --lat 31.15020077 \
  --lon 121.15577272 \
  --alt 8.02 \
  --duration 60 \
  --gga-interval 5
```

`--duration 0` 表示持续运行，按 `Ctrl+C` 停止。

## GUI 使用流程

1. 在“串口”页选择接收机对应设备，例如 `/dev/ttyUSB0` 或 `/dev/ttyUSB1`，并设置正确波特率。
2. 打开串口，确认原始数据窗口持续收到 NMEA 数据。
3. 在 NTRIP 配置区域填写 caster 地址、端口、挂载点、账号和密码。
4. 填写当前位置经纬度和高程，启动 NTRIP。
5. 观察 RTCM 类型、接收字节数、GGA quality 与定位状态；需要差分时启用 RTCM 串口转发。
6. 如需留档，在保存选项中指定原始数据的输出路径。

接收机串口必须处于可同时输出 NMEA、接收 RTCM 的模式；部分接收机切换到纯 RTCM 输入模式后，命令行与文本响应会停止，这是设备串口模式的正常行为。

## 配置与安全

默认配置在 `config.py`。其中的 NTRIP 地址、挂载点、账号和密码只适合本地受控环境。

向其他人交付工具前，请删除或替换 `config.py` 内的凭据。建议仅提供不含账号密码的配置模板，由实际使用者在 GUI 中填写，或在启动环境中设置：

```bash
export NTRIP_USERNAME='your_username'
export NTRIP_PASSWORD='your_password'
```

## 打包交付

### 32 位 x86 Linux 单文件程序

项目已包含可重复构建配置。它生成一个 32 位 x86 ELF 可执行文件，Python、PyQt5、pyserial 和 PyYAML 都会随程序交付；目标机无需安装 Python 或这些包。

构建机需要 Docker Buildx。x86_64 构建机还需要已启用 `linux/386` 仿真（Docker Desktop 通常已启用；Linux Docker 可通过 binfmt/QEMU 启用）：

```bash
./packaging/x86-linux/build.sh
file dist/x86-linux/gnss_raw_stream-x86-linux
```

预期 `file` 输出包含 `ELF 32-bit` 和 `Intel 80386`。将生成的单个文件复制到 32 位 x86 Linux 目标机后，赋予执行权限并运行：

```bash
chmod +x gnss_raw_stream-x86-linux
./gnss_raw_stream-x86-linux          # GUI
./gnss_raw_stream-x86-linux --help   # 命令行模式帮助
```

此项目依赖 Python 和 Qt。它们不能可靠地以传统 C/C++ 的“全静态链接”方式构建，尤其是 Qt 平台插件与 glibc；因此这里采用 PyInstaller 的单文件自包含交付方式。程序启动时会将 Qt 等运行时文件解包到私有临时目录，而不是使用目标机的 Python 包。目标机仍需具有与构建镜像兼容的 32 位 Linux 内核/动态加载器和基础图形环境。

如需 Windows x86 `.exe`，必须在 32 位 Windows 构建环境中重新运行 PyInstaller；Linux 上构建的 ELF 不能转换成 Windows `.exe`。

### GitHub Actions 自动发布

仓库内的 [GitHub Actions 工作流](.github/workflows/release-x86-linux.yml) 会在推送 `v*` 格式标签时构建并发布 x86 Linux 文件。例如：

```bash
git tag v1.0.0
git push origin v1.0.0
```

工作流使用 32 位 x86 Docker 镜像构建，验证产物是 `ELF 32-bit / Intel 80386`，然后把 `gnss_raw_stream-x86-linux` 上传为该标签对应 GitHub Release 的附件。每次工作流运行也会保留 30 天 Actions Artifact。

也可以从 GitHub 的 **Actions → Release x86 Linux → Run workflow** 手动运行：留空 tag 仅生成 Artifact；填写例如 `v1.0.1` 会同时创建或更新该 Release。

首次使用前，请确认仓库 **Settings → Actions → General → Workflow permissions** 设置为 **Read and write permissions**；否则工作流无法创建 Release。注意：`config.py` 中的默认 NTRIP 凭据会被编入发布文件，发布前应先移除或替换它们。
