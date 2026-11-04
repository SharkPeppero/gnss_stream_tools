CRC24Q_POLY = 0x1864CFB


RTCM_NAMES = {
    1005: "Reference Station ARP",
    1006: "Reference Station ARP + Height",
    1004: "GPS L1/L2 legacy",
    1012: "GLONASS L1/L2 legacy",
    1074: "GPS MSM4",
    1075: "GPS MSM5",
    1076: "GPS MSM6",
    1077: "GPS MSM7",
    1084: "GLONASS MSM4",
    1085: "GLONASS MSM5",
    1086: "GLONASS MSM6",
    1087: "GLONASS MSM7",
    1094: "Galileo MSM4",
    1095: "Galileo MSM5",
    1096: "Galileo MSM6",
    1097: "Galileo MSM7",
    1104: "SBAS MSM4",
    1107: "SBAS MSM7",
    1114: "QZSS MSM4",
    1117: "QZSS MSM7",
    1124: "BeiDou MSM4",
    1125: "BeiDou MSM5",
    1126: "BeiDou MSM6",
    1127: "BeiDou MSM7",
    1134: "NavIC MSM4",
    1137: "NavIC MSM7",
    1230: "GLONASS Code-Phase Bias",
}


def crc24q(data: bytes) -> int:
    crc = 0

    for byte in data:
        crc ^= byte << 16

        for _ in range(8):
            crc <<= 1

            if crc & 0x1000000:
                crc ^= CRC24Q_POLY

        crc &= 0xFFFFFF

    return crc


def get_bits(data: bytes, bit_offset: int, bit_length: int) -> int:
    result = 0

    for i in range(bit_length):
        byte_index = (bit_offset + i) // 8
        bit_index = 7 - ((bit_offset + i) % 8)

        result <<= 1
        result |= (data[byte_index] >> bit_index) & 1

    return result


class RTCMParser:
    def __init__(self):
        self.buffer = bytearray()

    def feed(self, data: bytes):
        self.buffer.extend(data)
        frames = []

        while True:
            if len(self.buffer) < 6:
                break

            if self.buffer[0] != 0xD3:
                index = self.buffer.find(b"\xD3")

                if index < 0:
                    self.buffer.clear()
                    break

                del self.buffer[:index]

                if len(self.buffer) < 6:
                    break

            length = ((self.buffer[1] & 0x03) << 8) | self.buffer[2]
            frame_size = 3 + length + 3

            if len(self.buffer) < frame_size:
                break

            frame = bytes(self.buffer[:frame_size])
            del self.buffer[:frame_size]

            recv_crc = (
                (frame[-3] << 16)
                | (frame[-2] << 8)
                | frame[-1]
            )
            calc_crc = crc24q(frame[:-3])
            payload = frame[3:3 + length]

            frames.append(
                {
                    "raw": frame,
                    "payload": payload,
                    "crc_ok": recv_crc == calc_crc,
                    "length": length,
                }
            )

        return frames


def decode_rtcm_header(payload: bytes):
    if len(payload) < 3:
        return None, None

    message_type = get_bits(payload, 0, 12)
    station_id = get_bits(payload, 12, 12)

    return message_type, station_id
