import binascii
import threading
import time
from collections import Counter, deque

from nmea import NMEA_TALKER_NAMES, nmea_checksum_ok
from rtcm import RTCM_NAMES
from stats import get_frequency


class RawStreamAnalyzer:
    def __init__(self):
        self.buffer = bytearray()
        self.start_time = time.monotonic()
        self.total_bytes = 0
        self.ascii_bytes = 0
        self.binary_bytes = 0
        self.line_count = 0
        self.nmea_count = Counter()
        self.nmea_crc_ok = 0
        self.nmea_crc_bad = 0
        self.latest_position = None
        self.binary_preview = ""
        self.last_lines = deque(maxlen=80)
        self.response_lines = deque(maxlen=200)
        self.lock = threading.Lock()

    def feed(self, data):
        with self.lock:
            position_changed = False
            chunk_has_binary = False
            responses = []
            self.total_bytes += len(data)

            for byte in data:
                if byte in (9, 10, 13) or 32 <= byte <= 126:
                    self.ascii_bytes += 1
                else:
                    self.binary_bytes += 1
                    chunk_has_binary = True

            self.buffer.extend(data)

            if chunk_has_binary:
                self.binary_preview = binascii.hexlify(data[-64:]).decode(
                    "ascii"
                )

            while b"\n" in self.buffer or b"\r" in self.buffer:
                indexes = [
                    index
                    for index in (
                        self.buffer.find(b"\n"),
                        self.buffer.find(b"\r"),
                    )
                    if index >= 0
                ]
                index = min(indexes)
                raw_line = bytes(self.buffer[:index + 1])
                del self.buffer[:index + 1]
                while self.buffer[:1] in (b"\n", b"\r"):
                    del self.buffer[:1]

                result = self._add_line(raw_line)

                if result["position_changed"]:
                    position_changed = True
                if result["response"]:
                    responses.append(result["response"])

            if len(self.buffer) > 8192:
                self.binary_preview = binascii.hexlify(
                    bytes(self.buffer[-64:])
                ).decode("ascii")
                del self.buffer[:-120]

            return {
                "position": (
                    dict(self.latest_position)
                    if position_changed and self.latest_position is not None
                    else None
                ),
                "responses": responses,
            }

    def _add_line(self, raw_line):
        raw_line = raw_line.strip()

        if not raw_line:
            return {"position_changed": False, "response": None}

        if not self._is_readable_bytes(raw_line):
            self.binary_preview = binascii.hexlify(raw_line[-64:]).decode(
                "ascii"
            )
            return {"position_changed": False, "response": None}

        line = raw_line.decode("ascii", errors="replace").strip()

        if not line:
            return {"position_changed": False, "response": None}

        nmea_index = line.find("$")
        novatel_index = line.find("#")

        if nmea_index > 0 and self._is_readable_text(line[nmea_index:]):
            line = line[nmea_index:]
        elif novatel_index > 0 and self._is_readable_text(line[novatel_index:]):
            line = line[novatel_index:]

        self.line_count += 1
        position_changed = False

        if line.startswith("$"):
            self.last_lines.append(line)
            body = line[1:].split("*", 1)[0]
            msg_id = body.split(",", 1)[0]
            checksum_ok = nmea_checksum_ok(line)

            if len(msg_id) >= 5:
                talker = msg_id[:2]
                message = msg_id[2:]
                self.nmea_count[f"{talker}/{message}"] += 1

                if message == "GGA" and checksum_ok:
                    position_changed = self._update_gga_position(line)

            if checksum_ok:
                self.nmea_crc_ok += 1
            else:
                self.nmea_crc_bad += 1

        elif line.startswith("#"):
            self.last_lines.append(line)
            message = line[1:].split(",", 1)[0]

            if message:
                self.nmea_count[f"NOVATEL/{message}"] += 1
        elif self._is_readable_text(line):
            self.response_lines.append(line)
            return {"position_changed": False, "response": line}

        return {"position_changed": position_changed, "response": None}

    @staticmethod
    def _is_readable_bytes(data):
        if not data:
            return False

        printable = sum(
            1
            for byte in data
            if byte in (9, 10, 13) or 32 <= byte <= 126
        )

        return printable / max(len(data), 1) >= 0.85

    @staticmethod
    def _is_readable_text(line):
        if not line:
            return False

        printable = sum(
            1
            for char in line
            if char == "\t" or 32 <= ord(char) <= 126
        )

        return printable / max(len(line), 1) >= 0.85

    def _update_gga_position(self, line):
        parts = line.split(",")

        if len(parts) < 10:
            return False

        lat_raw, lat_dir = parts[2], parts[3]
        lon_raw, lon_dir = parts[4], parts[5]

        if not lat_raw or not lon_raw:
            return False

        try:
            lat = self._nmea_to_decimal(lat_raw, lat_dir)
            lon = self._nmea_to_decimal(lon_raw, lon_dir)
            quality = int(parts[6]) if parts[6] else 0
            num_sats = int(parts[7]) if parts[7] else 0
            hdop = float(parts[8]) if parts[8] else 99.0
            altitude = float(parts[9]) if parts[9] else 0.0
        except ValueError:
            return False

        self.latest_position = {
            "lat": lat,
            "lon": lon,
            "alt": altitude,
            "quality": quality,
            "num_sats": num_sats,
            "hdop": hdop,
            "updated_at": time.monotonic(),
        }

        return True

    @staticmethod
    def _nmea_to_decimal(coord, direction):
        if not coord or "." not in coord:
            raise ValueError("invalid NMEA coordinate")

        point_index = coord.index(".")
        degrees = int(coord[:point_index - 2])
        minutes = float(coord[point_index - 2:])
        decimal = degrees + minutes / 60.0

        if direction in ("S", "W"):
            decimal = -decimal

        return decimal

    def summary(self):
        with self.lock:
            elapsed = time.monotonic() - self.start_time
            ascii_ratio = self.ascii_bytes / max(self.total_bytes, 1) * 100.0

            return {
                "elapsed": elapsed,
                "total_bytes": self.total_bytes,
                "kbps": self.total_bytes / max(elapsed, 0.001) / 1024.0,
                "ascii_ratio": ascii_ratio,
                "binary_bytes": self.binary_bytes,
                "line_count": self.line_count,
                "nmea_crc_ok": self.nmea_crc_ok,
                "nmea_crc_bad": self.nmea_crc_bad,
                "latest_position": (
                    dict(self.latest_position)
                    if self.latest_position is not None
                    else None
                ),
                "binary_preview": self.binary_preview,
                "top": self.nmea_count.most_common(12),
                "lines": list(self.last_lines)[-20:],
                "responses": list(self.response_lines)[-80:],
            }


class RawDataSaver:
    def __init__(self, path, mode):
        self.path = path
        self.mode = mode
        self.file = None
        self.lock = threading.Lock()

    def open(self):
        if not self.path:
            return

        file_mode = "a" if self.mode in ("ascii", "hex") else "ab"
        self.file = open(self.path, file_mode)

    def write(self, data):
        if not self.file:
            return

        with self.lock:
            if self.mode == "ascii":
                self.file.write(data.decode("ascii", errors="replace"))
            elif self.mode == "hex":
                self.file.write(
                    binascii.hexlify(data).decode("ascii") + "\n"
                )
            else:
                self.file.write(data)

            self.file.flush()

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def format_rtcm_summary(stats):
    with stats.lock:
        elapsed = time.monotonic() - stats.start_time
        lines = [
            f"运行时间: {elapsed:.1f} s",
            f"接收数据: {stats.total_bytes / 1024.0:.1f} KB",
            f"平均速率: {stats.total_bytes / max(elapsed, 0.001) / 1024.0:.2f} KB/s",
            f"RTCM 帧: {stats.total_frames}",
            f"CRC 正常: {stats.valid_frames}",
            f"CRC 错误: {stats.bad_crc}",
            f"最大数据间隔: {stats.max_gap:.3f} s",
            "",
            "Station IDs:",
        ]

        if stats.station_ids:
            for station_id, count in stats.station_ids.most_common():
                lines.append(f"  {station_id}: {count}")
        else:
            lines.append("  None")

        lines.extend(["", "RTCM messages:"])

        if stats.msg_count:
            for msg_type in sorted(stats.msg_count):
                name = RTCM_NAMES.get(msg_type, "Unknown / vendor / other")
                freq = get_frequency(stats.msg_timestamps[msg_type])
                freq_text = "-" if freq is None else f"{freq:.2f} Hz"
                lines.append(
                    f"  {msg_type}: {stats.msg_count[msg_type]} | {freq_text} | {name}"
                )
        else:
            lines.append("  None")

    return "\n".join(lines)


def format_raw_summary(raw_analyzer):
    summary = raw_analyzer.summary()
    lines = [
        f"运行时间: {summary['elapsed']:.1f} s",
        f"接收数据: {summary['total_bytes'] / 1024.0:.1f} KB",
        f"平均速率: {summary['kbps']:.2f} KB/s",
        f"ASCII 比例: {summary['ascii_ratio']:.1f}%",
        f"Binary 字节: {summary['binary_bytes']}",
        f"文本行数: {summary['line_count']}",
        f"NMEA checksum OK/BAD: {summary['nmea_crc_ok']} / {summary['nmea_crc_bad']}",
    ]

    position = summary["latest_position"]

    if position is not None:
        lines.extend(
            [
                (
                    "最新 GGA 坐标: "
                    f"{position['lat']:.8f}, {position['lon']:.8f}, "
                    f"alt={position['alt']:.2f}m"
                ),
                (
                    "最新 GGA 状态: "
                    f"quality={position['quality']} "
                    f"sats={position['num_sats']} "
                    f"hdop={position['hdop']:.2f}"
                ),
            ]
        )

    lines.extend(["", "协议/消息统计:"])

    if summary["top"]:
        for key, count in summary["top"]:
            if "/" in key and not key.startswith("NOVATEL/"):
                talker, message = key.split("/", 1)
                talker_name = NMEA_TALKER_NAMES.get(talker, talker)
                lines.append(f"  {key:<14} {count:5d}  {talker_name} {message}")
            else:
                lines.append(f"  {key:<14} {count:5d}")
    else:
        lines.append("  None")

    lines.extend(["", "最近原始文本:"])

    if summary["lines"]:
        lines.extend(summary["lines"])
    else:
        lines.append("  None")

    if summary["binary_preview"]:
        lines.extend(
            [
                "",
                "最近 Binary HEX:",
                summary["binary_preview"],
            ]
        )

    return "\n".join(lines)


def format_response_summary(raw_analyzer):
    summary = raw_analyzer.summary()
    lines = [
        f"文本响应行数: {len(summary['responses'])}",
        "",
        "最近命令响应:",
    ]

    if summary["responses"]:
        lines.extend(summary["responses"])
    else:
        lines.append("  None")

    return "\n".join(lines)
