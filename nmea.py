import time


NMEA_TALKER_NAMES = {
    "GP": "GPS",
    "GL": "GLONASS",
    "GA": "Galileo",
    "GB": "BeiDou",
    "BD": "BeiDou",
    "GN": "Multi-GNSS",
    "GQ": "QZSS",
}


def decimal_to_nmea(value, is_lat):
    if is_lat:
        direction = "N" if value >= 0 else "S"
        deg_width = 2
    else:
        direction = "E" if value >= 0 else "W"
        deg_width = 3

    value = abs(value)
    degrees = int(value)
    minutes = (value - degrees) * 60.0
    nmea = f"{degrees:0{deg_width}d}{minutes:09.6f}"

    return nmea, direction


def make_gga(lat, lon, altitude):
    utc = time.gmtime()
    timestamp = (
        f"{utc.tm_hour:02d}"
        f"{utc.tm_min:02d}"
        f"{utc.tm_sec:02d}.00"
    )
    lat_nmea, ns = decimal_to_nmea(lat, True)
    lon_nmea, ew = decimal_to_nmea(lon, False)

    body = (
        f"GPGGA,"
        f"{timestamp},"
        f"{lat_nmea},{ns},"
        f"{lon_nmea},{ew},"
        f"1,12,1.0,"
        f"{altitude:.1f},M,"
        f"0.0,M,,"
    )

    checksum = 0

    for char in body:
        checksum ^= ord(char)

    return f"${body}*{checksum:02X}\r\n"


def nmea_checksum_ok(sentence):
    text = sentence.strip()

    if not text.startswith("$") or "*" not in text:
        return False

    body, checksum_text = text[1:].split("*", 1)

    try:
        expected = int(checksum_text[:2], 16)
    except ValueError:
        return False

    checksum = 0

    for char in body:
        checksum ^= ord(char)

    return checksum == expected
