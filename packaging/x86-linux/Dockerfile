# Build a 32-bit (i386/x86) Linux deliverable.  Build on an x86_64 host with
# Docker Buildx/QEMU enabled, or on a native 32-bit Linux builder.
FROM --platform=linux/386 i386/debian:bookworm-slim AS build

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-pyqt5 python3-serial python3-yaml pyinstaller \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

# PyInstaller produces one user-facing ELF file.  Python modules, PyQt5,
# pyserial and PyYAML are collected into it and unpacked privately at launch.
RUN pyinstaller --noconfirm --clean --onefile \
    --name gnss_raw_stream-x86-linux \
    --paths /app \
    --collect-all PyQt5 \
    --collect-all serial \
    --collect-all yaml \
    /app/gnss_raw_stream.py \
    && /app/dist/gnss_raw_stream-x86-linux --help >/dev/null

# `docker build --output` exports only this stage to the caller.
FROM scratch AS artifact
COPY --from=build /app/dist/gnss_raw_stream-x86-linux /gnss_raw_stream-x86-linux
