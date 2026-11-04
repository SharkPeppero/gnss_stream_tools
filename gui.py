import glob
import os
import stat
import sys
import time

try:
    import yaml
except ImportError:
    yaml = None

try:
    from serial.tools import list_ports
except ImportError:
    list_ports = None

try:
    from PyQt5.QtCore import QTimer
    from PyQt5.QtWidgets import (
        QApplication,
        QCheckBox,
        QComboBox,
        QFileDialog,
        QGridLayout,
        QGroupBox,
        QLabel,
        QLineEdit,
        QMainWindow,
        QMessageBox,
        QPushButton,
        QDoubleSpinBox,
        QSpinBox,
        QTabWidget,
        QTextEdit,
        QVBoxLayout,
        QWidget,
    )
except ImportError:
    QApplication = None

from config import (
    DEFAULT_ALT,
    DEFAULT_GGA_INTERVAL,
    DEFAULT_GNSS_CONFIG_COMMANDS,
    DEFAULT_HOST,
    DEFAULT_LAT,
    DEFAULT_LON,
    DEFAULT_MOUNTPOINT,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
)
from ntrip_worker import NtripStreamWorker
from raw_stream import (
    format_raw_summary,
    format_response_summary,
    format_rtcm_summary,
)
from serial_worker import SerialStreamWorker


if QApplication is not None:

    class GnssRawStreamWindow(QMainWindow):
        def __init__(self):
            super().__init__()
            self.serial_worker = None
            self.ntrip_worker = None
            self.last_position_log_time = 0
            self.rtcm_forward_bytes = 0
            self.last_rtcm_forward_log_time = 0
            self.last_missing_serial_log_time = 0
            self.setWindowTitle("GNSS Raw Stream / RTCM Analyzer")
            self.resize(1080, 760)

            self.ntrip_host_edit = QLineEdit(DEFAULT_HOST)
            self.ntrip_port_spin = QSpinBox()
            self.ntrip_port_spin.setRange(1, 65535)
            self.ntrip_port_spin.setValue(DEFAULT_PORT)
            self.ntrip_mountpoint_edit = QLineEdit(DEFAULT_MOUNTPOINT)
            self.ntrip_username_edit = QLineEdit(DEFAULT_USERNAME)
            self.ntrip_password_edit = QLineEdit(DEFAULT_PASSWORD)
            self.ntrip_password_edit.setEchoMode(QLineEdit.Password)

            self.lat_spin = QDoubleSpinBox()
            self.lat_spin.setRange(-90.0, 90.0)
            self.lat_spin.setDecimals(8)
            self.lat_spin.setValue(DEFAULT_LAT)

            self.lon_spin = QDoubleSpinBox()
            self.lon_spin.setRange(-180.0, 180.0)
            self.lon_spin.setDecimals(8)
            self.lon_spin.setValue(DEFAULT_LON)

            self.alt_spin = QDoubleSpinBox()
            self.alt_spin.setRange(-1000.0, 10000.0)
            self.alt_spin.setDecimals(2)
            self.alt_spin.setValue(DEFAULT_ALT)

            self.gga_interval_spin = QDoubleSpinBox()
            self.gga_interval_spin.setRange(1.0, 120.0)
            self.gga_interval_spin.setDecimals(1)
            self.gga_interval_spin.setValue(DEFAULT_GGA_INTERVAL)

            self.open_ntrip_button = QPushButton("连接 NTRIP")
            self.open_ntrip_button.clicked.connect(self.open_ntrip)
            self.close_ntrip_button = QPushButton("断开 NTRIP")
            self.close_ntrip_button.setEnabled(False)
            self.close_ntrip_button.clicked.connect(self.close_stream)
            self.ntrip_status_label = QLabel("未连接")

            self.port_combo = QComboBox()
            self.port_combo.setEditable(True)
            self.last_port_devices = ()
            self.refresh_ports()

            self.baud_combo = QComboBox()
            self.baud_combo.addItems(
                [
                    "9600",
                    "19200",
                    "38400",
                    "57600",
                    "115200",
                    "230400",
                    "460800",
                    "921600",
                ]
            )
            self.baud_combo.setCurrentText("115200")

            self.save_check = QCheckBox("保存原始数据")
            self.save_path_edit = QLineEdit()
            self.save_path_edit.setPlaceholderText("选择保存路径")

            self.save_mode_combo = QComboBox()
            self.save_mode_combo.addItems(["ascii", "binary", "hex"])

            browse_button = QPushButton("浏览")
            browse_button.clicked.connect(self.choose_save_file)

            refresh_button = QPushButton("刷新串口")
            refresh_button.clicked.connect(self.refresh_ports)

            self.open_button = QPushButton("打开串口")
            self.open_button.clicked.connect(self.open_serial)

            self.close_button = QPushButton("关闭串口")
            self.close_button.setEnabled(False)
            self.close_button.clicked.connect(self.close_stream)

            self.send_config_button = QPushButton("下发默认配置")
            self.send_config_button.setEnabled(False)
            self.send_config_button.clicked.connect(self.send_default_config)

            self.command_edit = QLineEdit()
            self.command_edit.setPlaceholderText("输入自定义 GNSS 配置命令")

            self.send_command_button = QPushButton("发送命令")
            self.send_command_button.setEnabled(False)
            self.send_command_button.clicked.connect(self.send_custom_command)

            self.command_file_edit = QLineEdit()
            self.command_file_edit.setPlaceholderText("选择命令文件")

            self.choose_command_file_button = QPushButton("选择文件")
            self.choose_command_file_button.clicked.connect(
                self.choose_command_file
            )

            self.send_command_file_button = QPushButton("发送文件命令")
            self.send_command_file_button.setEnabled(False)
            self.send_command_file_button.clicked.connect(
                self.send_command_file
            )

            serial_group = self.build_serial_group(refresh_button)
            save_group = self.build_save_group(browse_button)
            ntrip_group = self.build_ntrip_group()
            config_group = self.build_config_group()

            self.rtcm_text = QTextEdit()
            self.rtcm_text.setReadOnly(True)

            self.raw_text = QTextEdit()
            self.raw_text.setReadOnly(True)

            self.response_text = QTextEdit()
            self.response_text.setReadOnly(True)

            self.log_text = QTextEdit()
            self.log_text.setReadOnly(True)

            tabs = QTabWidget()
            tabs.addTab(self.rtcm_text, "RTCM 信号分析")
            tabs.addTab(self.raw_text, "原始数据流分析")
            tabs.addTab(self.response_text, "命令响应")
            tabs.addTab(self.log_text, "通信日志")

            layout = QVBoxLayout()
            layout.addWidget(ntrip_group)
            layout.addWidget(serial_group)
            layout.addWidget(save_group)
            layout.addWidget(config_group)
            layout.addWidget(tabs, 1)

            central = QWidget()
            central.setLayout(layout)
            self.setCentralWidget(central)

            self.timer = QTimer(self)
            self.timer.timeout.connect(self.update_views)
            self.timer.start(1000)

            self.port_timer = QTimer(self)
            self.port_timer.timeout.connect(self.refresh_ports_if_changed)
            self.port_timer.start(1500)

        def build_serial_group(self, refresh_button):
            serial_group = QGroupBox("串口")
            serial_layout = QGridLayout()
            serial_layout.addWidget(QLabel("Port"), 0, 0)
            serial_layout.addWidget(self.port_combo, 0, 1)
            serial_layout.addWidget(QLabel("Baudrate"), 0, 2)
            serial_layout.addWidget(self.baud_combo, 0, 3)
            serial_layout.addWidget(refresh_button, 0, 4)
            serial_layout.addWidget(self.open_button, 0, 5)
            serial_layout.addWidget(self.close_button, 0, 6)
            serial_group.setLayout(serial_layout)

            return serial_group

        def build_save_group(self, browse_button):
            save_group = QGroupBox("保存数据")
            save_layout = QGridLayout()
            save_layout.addWidget(self.save_check, 0, 0)
            save_layout.addWidget(self.save_path_edit, 0, 1, 1, 4)
            save_layout.addWidget(browse_button, 0, 5)
            save_layout.addWidget(self.save_mode_combo, 0, 6)
            save_group.setLayout(save_layout)

            return save_group

        def build_ntrip_group(self):
            ntrip_group = QGroupBox("NTRIP 配置")
            ntrip_layout = QGridLayout()
            ntrip_layout.addWidget(QLabel("Host/IP"), 0, 0)
            ntrip_layout.addWidget(self.ntrip_host_edit, 0, 1)
            ntrip_layout.addWidget(QLabel("Port"), 0, 2)
            ntrip_layout.addWidget(self.ntrip_port_spin, 0, 3)
            ntrip_layout.addWidget(QLabel("Mountpoint"), 0, 4)
            ntrip_layout.addWidget(self.ntrip_mountpoint_edit, 0, 5)
            ntrip_layout.addWidget(self.open_ntrip_button, 0, 6)
            ntrip_layout.addWidget(self.close_ntrip_button, 0, 7)

            ntrip_layout.addWidget(QLabel("Username"), 1, 0)
            ntrip_layout.addWidget(self.ntrip_username_edit, 1, 1)
            ntrip_layout.addWidget(QLabel("Password"), 1, 2)
            ntrip_layout.addWidget(self.ntrip_password_edit, 1, 3)
            ntrip_layout.addWidget(QLabel("Lat"), 1, 4)
            ntrip_layout.addWidget(self.lat_spin, 1, 5)
            ntrip_layout.addWidget(QLabel("Lon"), 1, 6)
            ntrip_layout.addWidget(self.lon_spin, 1, 7)
            ntrip_layout.addWidget(QLabel("Alt/GGA(s)"), 2, 0)
            ntrip_layout.addWidget(self.alt_spin, 2, 1)
            ntrip_layout.addWidget(self.gga_interval_spin, 2, 2)
            ntrip_layout.addWidget(QLabel("状态"), 2, 3)
            ntrip_layout.addWidget(self.ntrip_status_label, 2, 4, 1, 4)
            ntrip_group.setLayout(ntrip_layout)

            return ntrip_group

        def build_config_group(self):
            config_group = QGroupBox("GNSS 模块配置")
            config_layout = QGridLayout()
            config_layout.addWidget(QLabel("默认命令"), 0, 0)
            config_layout.addWidget(
                QLabel(", ".join(DEFAULT_GNSS_CONFIG_COMMANDS)),
                0,
                1,
                1,
                4,
            )
            config_layout.addWidget(self.send_config_button, 0, 5)
            config_layout.addWidget(self.command_edit, 1, 0, 1, 5)
            config_layout.addWidget(self.send_command_button, 1, 5)
            config_layout.addWidget(self.command_file_edit, 2, 0, 1, 4)
            config_layout.addWidget(self.choose_command_file_button, 2, 4)
            config_layout.addWidget(self.send_command_file_button, 2, 5)
            config_group.setLayout(config_layout)

            return config_group

        def refresh_ports(self):
            current_device = self.port_combo.currentData()

            if current_device is None:
                current_text = self.port_combo.currentText().strip()
                current_device = current_text.split()[0] if current_text else ""

            self.port_combo.clear()
            port_items = self.build_serial_port_items()

            if not port_items:
                port_items = [
                    (device, device)
                    for device in ["/dev/ttyUSB0", "/dev/ttyUSB1", "/dev/ttyACM0", "COM1"]
                ]

            for label, device in port_items:
                self.port_combo.addItem(label, device)

            if current_device:
                index = self.port_combo.findData(current_device)

                if index >= 0:
                    self.port_combo.setCurrentIndex(index)

            self.last_port_devices = tuple(
                self.port_combo.itemData(i)
                for i in range(self.port_combo.count())
            )

        def refresh_ports_if_changed(self):
            devices = tuple(
                device for _, device in self.build_serial_port_items()
            )

            if devices == self.last_port_devices:
                return

            previous_device = self.port_combo.currentData()
            self.refresh_ports()

            if previous_device and previous_device not in devices:
                self.append_log(f"串口已移除: {previous_device}")

        def build_serial_port_items(self):
            items = []
            seen_paths = set()
            seen_targets = set()

            if list_ports is not None:
                ports = sorted(
                    list_ports.comports(),
                    key=self.port_sort_key,
                )

                for port in ports:
                    self.add_serial_port_item(
                        items,
                        seen_paths,
                        seen_targets,
                        self.format_port_label(port),
                        port.device,
                    )

            for device in self.find_extra_serial_devices():
                self.add_serial_port_item(
                    items,
                    seen_paths,
                    seen_targets,
                    self.format_extra_port_label(device),
                    device,
                )

            return items

        def add_serial_port_item(
            self,
            items,
            seen_paths,
            seen_targets,
            label,
            device,
        ):
            if not device:
                return

            target = os.path.realpath(device)

            if device in seen_paths or target in seen_targets:
                return

            items.append((label, device))
            seen_paths.add(device)
            seen_targets.add(target)

        def port_sort_key(self, port):
            device = port.device or ""
            has_usb_info = bool(port.vid is not None or port.hwid != "n/a")
            priority = 0 if has_usb_info else 1

            if "ACM" in device or "USB" in device:
                priority = -1

            return (priority, device)

        def find_extra_serial_devices(self):
            devices = []

            for pattern in (
                "/dev/ttyUART*",
                "/dev/serial/by-id/*",
                "/dev/serial/by-path/*",
            ):
                for device in sorted(glob.glob(pattern)):
                    if not self.is_serial_device_path(device):
                        continue

                    devices.append(device)

            return devices

        def is_serial_device_path(self, device):
            if not os.path.exists(device):
                return False

            target = os.path.realpath(device)

            try:
                mode = os.stat(target).st_mode
            except OSError:
                return False

            return stat.S_ISCHR(mode)

        def format_extra_port_label(self, device):
            target = os.path.realpath(device)

            if target != device:
                return f"{device}  -> {target}"

            return device

        def format_port_label(self, port):
            parts = [port.device]

            if port.description and port.description != "n/a":
                parts.append(port.description)

            details = []

            if port.manufacturer:
                details.append(port.manufacturer)
            if port.serial_number:
                details.append(f"SN={port.serial_number}")
            elif port.hwid and port.hwid != "n/a":
                details.append(port.hwid)

            if details:
                parts.append(f"({' '.join(details)})")

            return "  ".join(parts)

        def choose_save_file(self):
            path, _ = QFileDialog.getSaveFileName(
                self,
                "保存原始 GNSS 数据流",
                os.path.expanduser("~/gnss_raw_stream.log"),
                "All Files (*)",
            )

            if path:
                self.save_path_edit.setText(path)
                self.save_check.setChecked(True)

        def choose_command_file(self):
            path, _ = QFileDialog.getOpenFileName(
                self,
                "选择 GNSS 配置命令文件",
                os.path.expanduser("~"),
                "Text/YAML Files (*.txt *.cmd *.cfg *.yaml *.yml);;All Files (*)",
            )

            if path:
                self.command_file_edit.setText(path)

        def read_config_params(self, path):
            if yaml is None:
                raise RuntimeError("请先安装 PyYAML，才能读取 YAML 配置文件。")

            with open(path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}

            if not isinstance(data, dict):
                raise RuntimeError("配置文件格式不是 YAML 字典。")

            params = self.flatten_config(data)
            ros_params = params.get("ros__parameters")

            if isinstance(ros_params, dict):
                params.update(self.flatten_config(ros_params))

            return params

        def flatten_config(self, value):
            result = {}

            if not isinstance(value, dict):
                return result

            for key, item in value.items():
                result[str(key)] = item

                if isinstance(item, dict):
                    result.update(self.flatten_config(item))

            return result

        def open_serial(self):
            if self.serial_worker:
                return

            if SerialStreamWorker is None:
                QMessageBox.warning(
                    self,
                    "缺少依赖",
                    "请先安装 PyQt5 和 pyserial。",
                )
                return

            save_path = ""

            if self.save_check.isChecked():
                save_path = self.save_path_edit.text().strip()

                if not save_path:
                    QMessageBox.warning(
                        self,
                        "缺少保存路径",
                        "已勾选保存原始数据，请先选择保存路径。",
                    )
                    return

            port = self.selected_serial_port()

            if not port:
                QMessageBox.warning(self, "缺少串口", "请选择或输入串口设备。")
                return

            self.serial_worker = SerialStreamWorker(
                port,
                int(self.baud_combo.currentText()),
                save_path,
                self.save_mode_combo.currentText(),
            )
            self.serial_worker.log.connect(self.append_log)
            self.serial_worker.position_changed.connect(
                self.update_ntrip_position_from_serial
            )
            self.serial_worker.data_changed.connect(self.update_views)
            self.serial_worker.stopped.connect(self.on_serial_worker_stopped)
            self.serial_worker.start()

            self.open_button.setEnabled(False)
            self.close_button.setEnabled(True)
            self.send_config_button.setEnabled(True)
            self.send_command_button.setEnabled(True)
            self.send_command_file_button.setEnabled(True)

        def selected_serial_port(self):
            current_text = self.port_combo.currentText().strip()
            current_index = self.port_combo.currentIndex()

            if (
                current_text
                and current_index >= 0
                and current_text != self.port_combo.itemText(current_index)
            ):
                return current_text.split()[0]

            current_data = self.port_combo.currentData()

            if current_data:
                return current_data

            if not current_text:
                return ""

            return current_text.split()[0]

        def open_ntrip(self):
            if self.ntrip_worker:
                return

            if NtripStreamWorker is None:
                QMessageBox.warning(
                    self,
                    "缺少依赖",
                    "请先安装 PyQt5。",
                )
                return

            if not self.ntrip_host_edit.text().strip():
                QMessageBox.warning(self, "缺少参数", "请输入 NTRIP Host/IP。")
                return

            if not self.ntrip_username_edit.text().strip():
                QMessageBox.warning(self, "缺少参数", "请输入 NTRIP 账号。")
                return

            if not self.ntrip_password_edit.text():
                QMessageBox.warning(self, "缺少参数", "请输入 NTRIP 密码。")
                return

            save_path = ""

            if self.save_check.isChecked():
                save_path = self.save_path_edit.text().strip()

                if not save_path:
                    QMessageBox.warning(
                        self,
                        "缺少保存路径",
                        "已勾选保存原始数据，请先选择保存路径。",
                    )
                    return

            self.rtcm_forward_bytes = 0
            self.last_rtcm_forward_log_time = 0
            self.last_missing_serial_log_time = 0

            self.ntrip_worker = NtripStreamWorker(
                self.ntrip_host_edit.text().strip(),
                self.ntrip_port_spin.value(),
                self.ntrip_mountpoint_edit.text().strip(),
                self.ntrip_username_edit.text().strip(),
                self.ntrip_password_edit.text(),
                self.lat_spin.value(),
                self.lon_spin.value(),
                self.alt_spin.value(),
                self.gga_interval_spin.value(),
                save_path,
                self.save_mode_combo.currentText(),
            )
            self.ntrip_worker.log.connect(self.append_log)
            self.ntrip_worker.status_changed.connect(self.set_ntrip_status)
            self.ntrip_worker.rtcm_received.connect(self.forward_rtcm_to_serial)
            self.ntrip_worker.data_changed.connect(self.update_views)
            self.ntrip_worker.stopped.connect(self.on_ntrip_worker_stopped)
            self.ntrip_worker.start()
            self.set_ntrip_status("连接中")

            self.open_ntrip_button.setEnabled(False)
            self.close_ntrip_button.setEnabled(True)

        def close_stream(self):
            sender = self.sender()

            if sender == self.close_ntrip_button:
                self.close_ntrip()
            elif sender == self.close_button:
                self.close_serial()
            else:
                self.close_ntrip()
                self.close_serial()

        def close_serial(self):
            if self.serial_worker:
                self.serial_worker.stop()

        def close_ntrip(self):
            if self.ntrip_worker:
                self.set_ntrip_status("断开中")
                self.ntrip_worker.stop()

        def on_serial_worker_stopped(self):
            self.serial_worker = None
            self.open_button.setEnabled(True)
            self.close_button.setEnabled(False)
            self.send_config_button.setEnabled(False)
            self.send_command_button.setEnabled(False)
            self.send_command_file_button.setEnabled(False)

        def on_ntrip_worker_stopped(self):
            self.ntrip_worker = None
            self.open_ntrip_button.setEnabled(True)
            self.close_ntrip_button.setEnabled(False)
            self.set_ntrip_status("未连接")

        def send_default_config(self):
            if not self.serial_worker:
                QMessageBox.warning(self, "串口未打开", "请先打开串口。")
                return

            for command in DEFAULT_GNSS_CONFIG_COMMANDS:
                self.serial_worker.send_line(command)
                time.sleep(0.05)

        def send_custom_command(self):
            if not self.serial_worker:
                QMessageBox.warning(self, "串口未打开", "请先打开串口。")
                return

            if self.command_edit.text().strip():
                self.serial_worker.send_line(self.command_edit.text())
                self.command_edit.clear()

        def send_command_file(self):
            if not self.serial_worker:
                QMessageBox.warning(self, "串口未打开", "请先打开串口。")
                return

            path = self.command_file_edit.text().strip()

            if not path:
                QMessageBox.warning(self, "缺少命令文件", "请先选择命令文件。")
                return

            try:
                commands = self.read_command_file(path)
            except Exception as e:
                QMessageBox.warning(self, "命令文件读取失败", str(e))
                return

            if not commands:
                QMessageBox.information(
                    self,
                    "没有可发送的命令",
                    "命令文件中没有非空命令行。",
                )
                return

            for command in commands:
                self.serial_worker.send_line(command)
                time.sleep(0.05)

            self.append_log(f"已发送 {len(commands)} 条文件命令: {path}")

        def read_command_file(self, path):
            if path.endswith((".yaml", ".yml")):
                if yaml is None:
                    raise RuntimeError("请先安装 PyYAML，才能读取 YAML 命令文件。")

                params = self.read_config_params(path)
                cmds = params.get("um982_cfg_cmd")

                if isinstance(cmds, (list, tuple)):
                    return [
                        str(cmd).strip().rstrip("\r\n")
                        for cmd in cmds
                        if str(cmd).strip()
                    ]

                return []

            commands = []

            with open(path, "r", encoding="utf-8") as f:
                for line in f:
                    command = line.strip().rstrip("\r\n")

                    if not command or command.startswith("#"):
                        continue

                    commands.append(command)

            return commands

        def set_ntrip_status(self, text):
            self.ntrip_status_label.setText(text)

        def update_ntrip_position_from_serial(
            self,
            lat,
            lon,
            altitude,
            quality,
            num_sats,
            hdop,
        ):
            self.lat_spin.setValue(lat)
            self.lon_spin.setValue(lon)
            self.alt_spin.setValue(altitude)

            if self.ntrip_worker:
                self.ntrip_worker.set_position(lat, lon, altitude)

            now = time.monotonic()
            if now - self.last_position_log_time >= 5.0:
                self.append_log(
                    "串口定位更新 NTRIP 坐标: "
                    f"lat={lat:.8f}, lon={lon:.8f}, alt={altitude:.2f}, "
                    f"quality={quality}, sats={num_sats}, hdop={hdop:.2f}"
                )
                self.last_position_log_time = now

        def forward_rtcm_to_serial(self, data):
            now = time.monotonic()

            if not self.serial_worker:
                if now - self.last_missing_serial_log_time >= 5.0:
                    self.append_log("WARN: 串口未打开，RTCM 差分未写入 UM982。")
                    self.last_missing_serial_log_time = now
                return

            written = self.serial_worker.write_bytes(data)

            if written <= 0:
                return

            self.rtcm_forward_bytes += written

            if now - self.last_rtcm_forward_log_time >= 5.0:
                self.append_log(
                    "RTCM -> 串口: "
                    f"{self.rtcm_forward_bytes / 1024.0:.1f} KB 已写入 UM982"
                )
                self.last_rtcm_forward_log_time = now

        def append_log(self, text):
            timestamp = time.strftime("%H:%M:%S")
            self.log_text.append(f"[{timestamp}] {text}")

        @staticmethod
        def set_text_preserve_scroll(text_edit, text):
            scroll_bar = text_edit.verticalScrollBar()
            old_value = scroll_bar.value()
            old_maximum = scroll_bar.maximum()
            at_bottom = old_value >= old_maximum

            text_edit.setPlainText(text)

            new_scroll_bar = text_edit.verticalScrollBar()
            if at_bottom:
                new_scroll_bar.setValue(new_scroll_bar.maximum())
            else:
                new_scroll_bar.setValue(
                    min(old_value, new_scroll_bar.maximum())
                )

        def update_views(self):
            rtcm_worker = self.ntrip_worker or self.serial_worker
            raw_worker = self.serial_worker or self.ntrip_worker

            if not rtcm_worker and not raw_worker:
                return

            if rtcm_worker:
                self.set_text_preserve_scroll(
                    self.rtcm_text,
                    format_rtcm_summary(rtcm_worker.stats)
                )

            if raw_worker:
                self.set_text_preserve_scroll(
                    self.raw_text,
                    format_raw_summary(raw_worker.raw_analyzer)
                )
                self.set_text_preserve_scroll(
                    self.response_text,
                    format_response_summary(raw_worker.raw_analyzer)
                )

        def closeEvent(self, event):
            if self.ntrip_worker:
                self.ntrip_worker.stop()
                self.ntrip_worker.wait(1500)

            if self.serial_worker:
                self.serial_worker.stop()
                self.serial_worker.wait(1500)

            event.accept()

else:
    GnssRawStreamWindow = None


def run_gui():
    if QApplication is None or GnssRawStreamWindow is None:
        print("ERROR: 请先安装 PyQt5 后再使用 --gui。")
        return 1

    app = QApplication(sys.argv)
    window = GnssRawStreamWindow()
    window.show()

    return app.exec_()
