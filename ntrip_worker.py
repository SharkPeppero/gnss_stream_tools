import base64
import socket
import threading
import time

try:
    from PyQt5.QtCore import QThread, pyqtSignal
except ImportError:
    QThread = None

from nmea import make_gga
from raw_stream import RawDataSaver, RawStreamAnalyzer
from rtcm import RTCMParser, decode_rtcm_header
from stats import Statistics


if QThread is not None:

    class NtripStreamWorker(QThread):
        log = pyqtSignal(str)
        status_changed = pyqtSignal(str)
        rtcm_received = pyqtSignal(bytes)
        data_changed = pyqtSignal()
        stopped = pyqtSignal()

        def __init__(
            self,
            host,
            port,
            mountpoint,
            username,
            password,
            lat,
            lon,
            altitude,
            gga_interval,
            save_path,
            save_mode,
        ):
            super().__init__()
            self.host = host
            self.port = port
            self.mountpoint = mountpoint
            self.username = username
            self.password = password
            self.lat = lat
            self.lon = lon
            self.altitude = altitude
            self.gga_interval = gga_interval
            self.stats = Statistics()
            self.rtcm_parser = RTCMParser()
            self.raw_analyzer = RawStreamAnalyzer()
            self.saver = RawDataSaver(save_path, save_mode)
            self.running = False
            self.sock = None
            self.send_lock = threading.Lock()
            self.position_lock = threading.Lock()

        def run(self):
            try:
                self.saver.open()
                remaining = self.connect_ntrip()
                self.running = True
                self.status_changed.emit(
                    f"已连接 {self.host}:{self.port}/{self.mountpoint}"
                )
                self.send_gga()

                gga_thread = threading.Thread(
                    target=self.gga_loop,
                    daemon=True,
                )
                gga_thread.start()

                if remaining:
                    self.process_data(remaining)

                while self.running:
                    try:
                        data = self.sock.recv(8192)

                        if not data:
                            self.log.emit("ERROR: NTRIP caster closed connection")
                            self.status_changed.emit("服务器已断开")
                            break

                        self.process_data(data)

                    except socket.timeout:
                        self.log.emit("WARN: 10 秒未收到 NTRIP 数据")

            except Exception as e:
                self.log.emit(f"ERROR: {e}")
                self.status_changed.emit(f"连接失败: {e}")

            finally:
                self.running = False
                self.saver.close()

                if self.sock:
                    try:
                        self.sock.close()
                    except Exception:
                        pass

                self.log.emit("NTRIP 已断开")
                self.status_changed.emit("未连接")
                self.stopped.emit()

        def connect_ntrip(self):
            self.log.emit(
                f"连接 NTRIP Host/IP: {self.host}:{self.port}/{self.mountpoint}"
            )
            self.status_changed.emit(
                f"连接中 {self.host}:{self.port}/{self.mountpoint}"
            )
            self.sock = socket.create_connection(
                (self.host, self.port),
                timeout=10,
            )
            self.sock.settimeout(10)

            auth_raw = f"{self.username}:{self.password}".encode()
            auth = base64.b64encode(auth_raw).decode()
            request = (
                f"GET /{self.mountpoint} HTTP/1.1\r\n"
                f"Host: {self.host}:{self.port}\r\n"
                f"Ntrip-Version: Ntrip/2.0\r\n"
                f"User-Agent: GNSS-RAW-STREAM-GUI/1.0\r\n"
                f"Authorization: Basic {auth}\r\n"
                f"Connection: keep-alive\r\n"
                f"\r\n"
            )
            self.sock.sendall(request.encode())

            response = b""

            while b"\r\n\r\n" not in response:
                chunk = self.sock.recv(4096)

                if not chunk:
                    raise RuntimeError("Caster closed connection")

                response += chunk

                if len(response) > 32768:
                    raise RuntimeError("NTRIP HTTP header too large")

            header, remaining = response.split(b"\r\n\r\n", 1)
            first_line = header.split(b"\r\n")[0]
            success = b"200" in first_line or first_line.startswith(b"ICY 200")

            self.log.emit(first_line.decode(errors="replace"))

            if not success:
                raise RuntimeError(
                    "NTRIP connection rejected: "
                    f"{first_line.decode(errors='replace')}"
                )

            self.log.emit("NTRIP 认证成功")

            return remaining

        def send_gga(self):
            with self.position_lock:
                lat = self.lat
                lon = self.lon
                altitude = self.altitude

            gga = make_gga(lat, lon, altitude)

            with self.send_lock:
                self.sock.sendall(gga.encode())

            self.log.emit(f"GGA -> caster: {gga.strip()}")

        def gga_loop(self):
            while self.running:
                time.sleep(self.gga_interval)

                if not self.running:
                    break

                try:
                    self.send_gga()
                except Exception as e:
                    self.log.emit(f"WARN: GGA 发送失败: {e}")

        def process_data(self, data):
            self.stats.add_bytes(len(data))
            self.raw_analyzer.feed(data)
            self.saver.write(data)
            self.rtcm_received.emit(data)

            frames = self.rtcm_parser.feed(data)

            for frame in frames:
                msg_type, station_id = decode_rtcm_header(frame["payload"])
                self.stats.add_frame(msg_type, station_id, frame["crc_ok"])

            self.data_changed.emit()

        def stop(self):
            self.running = False

            if self.sock:
                try:
                    self.sock.shutdown(socket.SHUT_RDWR)
                except Exception:
                    pass

        def set_position(self, lat, lon, altitude):
            with self.position_lock:
                self.lat = lat
                self.lon = lon
                self.altitude = altitude

else:
    NtripStreamWorker = None
