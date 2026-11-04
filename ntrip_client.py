import base64
import socket
import threading
import time

from nmea import make_gga
from rtcm import RTCMParser, decode_rtcm_header


class NTRIPClient:
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
        stats,
    ):
        self.host = host
        self.port = port
        self.mountpoint = mountpoint
        self.username = username
        self.password = password
        self.lat = lat
        self.lon = lon
        self.altitude = altitude
        self.gga_interval = gga_interval
        self.stats = stats
        self.sock = None
        self.running = False

    def connect(self):
        print()
        print("============================================================")
        print("Connecting NTRIP")
        print("============================================================")
        print(f"Host/IP    : {self.host}:{self.port}")
        print(f"Mountpoint : {self.mountpoint}")
        print(f"Position   : {self.lat:.8f}, {self.lon:.8f}")
        print()

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
            f"User-Agent: NTRIP RTK-DIAG/1.0\r\n"
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
        print(header.decode(errors="replace"))
        print()

        first_line = header.split(b"\r\n")[0]
        success = b"200" in first_line or first_line.startswith(b"ICY 200")

        if not success:
            raise RuntimeError(
                f"NTRIP connection rejected: "
                f"{first_line.decode(errors='replace')}"
            )

        print("[OK] NTRIP authentication successful")
        print()
        self.running = True
        self.send_gga()

        return remaining

    def send_gga(self):
        gga = make_gga(self.lat, self.lon, self.altitude)

        try:
            self.sock.sendall(gga.encode())
            print(f"[GGA -> caster] {gga.strip()}")
        except Exception as e:
            print(f"[WARN] Failed to send GGA: {e}")

    def gga_loop(self):
        while self.running:
            time.sleep(self.gga_interval)

            if not self.running:
                break

            self.send_gga()

    def receive(self, duration):
        parser = RTCMParser()
        initial = self.connect()
        gga_thread = threading.Thread(
            target=self.gga_loop,
            daemon=True,
        )
        gga_thread.start()

        if initial:
            self.process_data(parser, initial)

        start = time.monotonic()
        last_print = start

        try:
            while self.running:
                if duration > 0 and time.monotonic() - start >= duration:
                    break

                try:
                    data = self.sock.recv(8192)

                    if not data:
                        print("\n[ERROR] Caster closed connection")
                        break

                    self.process_data(parser, data)

                except socket.timeout:
                    print("\n[WARN] 10 seconds without any NTRIP data!")

                now = time.monotonic()

                if now - last_print >= 1.0:
                    self.print_live()
                    last_print = now

        finally:
            self.running = False

            try:
                self.sock.close()
            except Exception:
                pass

    def process_data(self, parser, data):
        self.stats.add_bytes(len(data))
        frames = parser.feed(data)

        for frame in frames:
            msg_type, station_id = decode_rtcm_header(frame["payload"])
            self.stats.add_frame(msg_type, station_id, frame["crc_ok"])

    def print_live(self):
        with self.stats.lock:
            elapsed = time.monotonic() - self.stats.start_time
            kbps = self.stats.total_bytes / max(elapsed, 0.001) / 1024.0
            top_msgs = self.stats.msg_count.most_common(6)
            msg_text = " ".join(f"{m}:{count}" for m, count in top_msgs)

            print(
                f"\r"
                f"RX={kbps:6.2f} KB/s | "
                f"frames={self.stats.total_frames:5d} | "
                f"CRC_ERR={self.stats.bad_crc:3d} | "
                f"max_gap={self.stats.max_gap:5.2f}s | "
                f"{msg_text:<40}",
                end="",
                flush=True,
            )
