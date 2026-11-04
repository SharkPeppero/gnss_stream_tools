#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os
import sys

CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

if CURRENT_DIR not in sys.path:
    sys.path.insert(0, CURRENT_DIR)

from config import (  # noqa: E402
    DEFAULT_ALT,
    DEFAULT_GGA_INTERVAL,
    DEFAULT_HOST,
    DEFAULT_LAT,
    DEFAULT_LON,
    DEFAULT_MOUNTPOINT,
    DEFAULT_PASSWORD,
    DEFAULT_PORT,
    DEFAULT_USERNAME,
)
from diagnostics import diagnose  # noqa: E402
from gui import run_gui  # noqa: E402
from ntrip_client import NTRIPClient  # noqa: E402
from stats import Statistics  # noqa: E402


def parse_args():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--gui",
        action="store_true",
        help="启动 GNSS 原始流/RTCM 分析 GUI",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help="NTRIP caster 地址，可以是 IP 或域名",
    )
    parser.add_argument("--port", type=int, default=DEFAULT_PORT)
    parser.add_argument("--mountpoint", default=DEFAULT_MOUNTPOINT)
    parser.add_argument("--lat", type=float, default=DEFAULT_LAT)
    parser.add_argument("--lon", type=float, default=DEFAULT_LON)
    parser.add_argument("--alt", type=float, default=DEFAULT_ALT)
    parser.add_argument(
        "--duration",
        type=float,
        default=60,
        help="测试时间，秒，0=一直运行",
    )
    parser.add_argument(
        "--gga-interval",
        type=float,
        default=DEFAULT_GGA_INTERVAL,
    )

    return parser.parse_args()


def run_cli(args):
    if not args.host.strip():
        print("[ERROR] --host 不能为空，可以填写 IP 或域名")
        return 2

    username = os.getenv("NTRIP_USERNAME", DEFAULT_USERNAME)
    password = os.getenv("NTRIP_PASSWORD", DEFAULT_PASSWORD)

    stats = Statistics()
    client = NTRIPClient(
        host=args.host,
        port=args.port,
        mountpoint=args.mountpoint,
        username=username,
        password=password,
        lat=args.lat,
        lon=args.lon,
        altitude=args.alt,
        gga_interval=args.gga_interval,
        stats=stats,
    )

    try:
        client.receive(args.duration)
    except KeyboardInterrupt:
        print("\nCtrl+C")
    except Exception as e:
        print(f"\n[ERROR] {e}")
    finally:
        diagnose(stats)

    return 0


def main():
    args = parse_args()

    if args.gui or len(sys.argv) == 1:
        return run_gui()

    return run_cli(args)


if __name__ == "__main__":
    sys.exit(main())
