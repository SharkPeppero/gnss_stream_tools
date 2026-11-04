import threading
import time
from collections import Counter, defaultdict, deque


class Statistics:
    def __init__(self):
        self.start_time = time.monotonic()
        self.total_bytes = 0
        self.total_frames = 0
        self.valid_frames = 0
        self.bad_crc = 0
        self.msg_count = Counter()
        self.station_ids = Counter()
        self.msg_timestamps = defaultdict(lambda: deque(maxlen=10000))
        self.last_data_time = None
        self.data_gaps = deque(maxlen=10000)
        self.max_gap = 0.0
        self.lock = threading.Lock()

    def add_bytes(self, size):
        now = time.monotonic()

        with self.lock:
            self.total_bytes += size

            if self.last_data_time is not None:
                gap = now - self.last_data_time
                self.data_gaps.append(gap)

                if gap > self.max_gap:
                    self.max_gap = gap

            self.last_data_time = now

    def add_frame(self, msg_type, station_id, crc_ok):
        now = time.monotonic()

        with self.lock:
            self.total_frames += 1

            if crc_ok:
                self.valid_frames += 1
            else:
                self.bad_crc += 1

            if msg_type is not None:
                self.msg_count[msg_type] += 1
                self.msg_timestamps[msg_type].append(now)

            if station_id is not None:
                self.station_ids[station_id] += 1


def get_frequency(timestamps):
    if len(timestamps) < 2:
        return None

    intervals = []
    previous = timestamps[0]

    for timestamp in list(timestamps)[1:]:
        diff = timestamp - previous

        if diff > 0:
            intervals.append(diff)

        previous = timestamp

    if not intervals:
        return None

    avg = sum(intervals) / len(intervals)

    if avg <= 0:
        return None

    return 1.0 / avg
