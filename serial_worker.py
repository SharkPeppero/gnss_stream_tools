import threading

try:
    import serial
except ImportError:
    serial = None

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except ImportError:
    QThread = None

from raw_stream import RawDataSaver, RawStreamAnalyzer
from rtcm import RTCMParser, decode_rtcm_header
from stats import Statistics


if QThread is not None:

    class SerialStreamWorker(QThread):
        log = pyqtSignal(str)
        position_changed = pyqtSignal(float, float, float, int, int, float)
        data_changed = pyqtSignal()
        stopped = pyqtSignal()

        def __init__(self, port, baudrate, save_path, save_mode):
            super().__init__()
            self.port = port
            self.baudrate = baudrate
            self.stats = Statistics()
            self.rtcm_parser = RTCMParser()
            self.raw_analyzer = RawStreamAnalyzer()
            self.saver = RawDataSaver(save_path, save_mode)
            self.running = False
            self.serial_port = None
            self.write_lock = threading.Lock()

        def run(self):
            if serial is None:
                self.log.emit("ERROR: 未安装 pyserial，无法打开串口。")
                self.stopped.emit()
                return

            try:
                self.saver.open()
                self.serial_port = serial.Serial(
                    self.port,
                    self.baudrate,
                    timeout=0.2,
                )
                self.running = True
                self.log.emit(
                    f"串口已打开: {self.port}, baudrate={self.baudrate}"
                )

                while self.running:
                    data = self.serial_port.read(8192)

                    if not data:
                        continue

                    self.stats.add_bytes(len(data))
                    result = self.raw_analyzer.feed(data)
                    position = result["position"]
                    self.saver.write(data)

                    if position is not None:
                        self.position_changed.emit(
                            position["lat"],
                            position["lon"],
                            position["alt"],
                            position["quality"],
                            position["num_sats"],
                            position["hdop"],
                        )

                    for response in result["responses"]:
                        self.log.emit(f"RX <- {response}")

                    frames = self.rtcm_parser.feed(data)

                    for frame in frames:
                        msg_type, station_id = decode_rtcm_header(
                            frame["payload"]
                        )
                        self.stats.add_frame(
                            msg_type,
                            station_id,
                            frame["crc_ok"],
                        )

                    self.data_changed.emit()

            except Exception as e:
                self.log.emit(f"ERROR: {e}")

            finally:
                self.running = False
                self.saver.close()

                if self.serial_port:
                    try:
                        self.serial_port.close()
                    except Exception:
                        pass

                self.log.emit("串口已关闭")
                self.stopped.emit()

        def stop(self):
            self.running = False

        def send_line(self, line):
            if not self.serial_port or not self.serial_port.is_open:
                self.log.emit("WARN: 串口未打开，无法下发配置。")
                return

            data = line.strip().encode("ascii") + b"\r\n"

            with self.write_lock:
                self.serial_port.write(data)
                self.serial_port.flush()

            self.log.emit(f"TX -> {line.strip()}")

        def write_bytes(self, data):
            if not self.serial_port or not self.serial_port.is_open:
                self.log.emit("WARN: 串口未打开，无法写入 RTCM。")
                return 0

            with self.write_lock:
                written = self.serial_port.write(data)
                self.serial_port.flush()

            return written

else:
    SerialStreamWorker = None
