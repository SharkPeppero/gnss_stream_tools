import time

from rtcm import RTCM_NAMES
from stats import get_frequency


def diagnose(stats):
    print()
    print()
    print("=" * 72)
    print("                  NTRIP / RTCM DIAGNOSIS")
    print("=" * 72)

    elapsed = time.monotonic() - stats.start_time

    print(f"Test duration        : {elapsed:.1f} s")
    print(f"Received             : {stats.total_bytes / 1024:.1f} KB")
    print(
        f"Average throughput   : "
        f"{stats.total_bytes / max(elapsed, 0.001) / 1024:.2f} KB/s"
    )
    print(f"RTCM frames          : {stats.total_frames}")
    print(f"Valid CRC            : {stats.valid_frames}")
    print(f"CRC errors           : {stats.bad_crc}")
    print(f"Max socket data gap  : {stats.max_gap:.3f} s")

    print()
    print("Station IDs:")

    if stats.station_ids:
        for station_id, count in stats.station_ids.most_common():
            print(f"  Station {station_id:<5} : {count} frames")
    else:
        print("  None")

    print()
    print("RTCM messages:")
    print("-" * 72)

    for msg_type in sorted(stats.msg_count):
        count = stats.msg_count[msg_type]
        name = RTCM_NAMES.get(msg_type, "Unknown / vendor / other")
        freq = get_frequency(stats.msg_timestamps[msg_type])
        freq_text = "-" if freq is None else f"{freq:.2f} Hz"
        print(f"{msg_type:4d} | {name:<32} | {count:5d} | {freq_text}")

    print()
    print("=" * 72)
    print("DIAGNOSIS")
    print("=" * 72)

    problems = []
    warnings = []
    ok = []

    if stats.total_bytes == 0:
        problems.append(
            "没有收到任何 NTRIP 数据：检查账号、挂载点、网络和 caster。"
        )
    else:
        ok.append("NTRIP caster 正在持续发送数据。")

    if stats.total_frames:
        crc_ratio = stats.bad_crc / stats.total_frames

        if crc_ratio > 0.01:
            problems.append(
                f"RTCM CRC 错误率达到 {crc_ratio * 100:.2f}%，"
                "需要检查网络数据、串口写入或数据截断。"
            )
        elif stats.bad_crc:
            warnings.append(f"存在 {stats.bad_crc} 个 CRC 错误帧。")
        else:
            ok.append("RTCM3 CRC 全部正常。")

    if stats.max_gap > 5:
        problems.append(
            f"NTRIP 数据最大断流 {stats.max_gap:.2f}s，"
            "这会严重影响 RTK Fixed。"
        )
    elif stats.max_gap > 2:
        warnings.append(
            f"NTRIP 最大数据间隔 {stats.max_gap:.2f}s，"
            "链路存在明显 jitter。"
        )
    else:
        ok.append(
            f"NTRIP 没发现明显长时间断流，"
            f"最大 socket gap={stats.max_gap:.2f}s。"
        )

    if 1005 in stats.msg_count or 1006 in stats.msg_count:
        ok.append("存在 RTCM 1005/1006 基准站坐标。")
    else:
        problems.append("没有检测到 RTCM 1005/1006 基准站坐标消息。")

    gps = any(x in stats.msg_count for x in [1074, 1075, 1076, 1077])
    glo = any(x in stats.msg_count for x in [1084, 1085, 1086, 1087])
    gal = any(x in stats.msg_count for x in [1094, 1095, 1096, 1097])
    bds = any(x in stats.msg_count for x in [1124, 1125, 1126, 1127])

    print()
    print("Constellations:")
    print(f"  GPS      : {'YES' if gps else 'NO'}")
    print(f"  GLONASS  : {'YES' if glo else 'NO'}")
    print(f"  Galileo  : {'YES' if gal else 'NO'}")
    print(f"  BeiDou   : {'YES' if bds else 'NO'}")

    constellation_count = sum([gps, glo, gal, bds])

    if constellation_count == 0:
        problems.append(
            "没有检测到 GPS/BDS/GAL/GLO 的 MSM 观测消息，"
            "该数据流不能正常进行常规 RTK。"
        )
    elif constellation_count == 1:
        warnings.append(
            "只发现一个 GNSS 星座的 MSM 数据，"
            "RTK Fixed 鲁棒性可能明显降低。"
        )
    else:
        ok.append(f"发现 {constellation_count} 个主要 GNSS 星座的 MSM 数据。")

    msm7 = any(x in stats.msg_count for x in [1077, 1087, 1097, 1127])
    msm4 = any(x in stats.msg_count for x in [1074, 1084, 1094, 1124])

    if msm7:
        ok.append("检测到 MSM7 高精度载波观测消息。")
    elif msm4:
        warnings.append("当前主要为 MSM4；可以 RTK，但建议确认服务商数据规格。")

    print_items("OK", "+", ok)
    print_items("WARN", "!", warnings)
    print_items("PROBLEM", "X", problems)

    print()
    print("=" * 72)

    if not problems:
        print(
            "NTRIP/RTCM 数据流没有发现能够直接解释 "
            "'长期 FLOAT' 的严重异常。"
        )
        print()
        print("如果 UM982 仍然 quality=5，下一步重点检查：")
        print("  1. Base-Rover 基线距离")
        print("  2. UM982 实际收到 RTCM 后的 GGA differential age")
        print("  3. 天线环境、多路径和载波 C/N0")
        print("  4. 是否发生频繁 cycle slip")
        print("  5. UM982 RTK 配置")
        print("  6. 基站坐标是否发生变化")
        print("  7. NTRIP 服务是否属于 VRS/MAC/FKP，以及是否依赖 rover GGA")
    else:
        print(
            "当前 NTRIP/RTCM 数据流存在明显问题，"
            "建议先解决上面的 PROBLEM 再判断 UM982。"
        )

    print("=" * 72)


def print_items(title, prefix, items):
    print()
    print(f"[{title}]")

    if items:
        for item in items:
            print(f"  {prefix} {item}")
    else:
        print("  None")
