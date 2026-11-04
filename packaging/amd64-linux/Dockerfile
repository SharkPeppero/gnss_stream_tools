FROM --platform=linux/amd64 debian:bookworm-slim AS build

WORKDIR /app

RUN apt-get update \
    && DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends \
        python3 python3-pyqt5 python3-serial python3-yaml pyinstaller \
    && rm -rf /var/lib/apt/lists/*

COPY . /app

RUN pyinstaller --noconfirm --clean --onefile \
    --name gnss_raw_stream-amd64-linux \
    --paths /app \
    --collect-all PyQt5 \
    --collect-all serial \
    --collect-all yaml \
    /app/gnss_raw_stream.py \
    && /app/dist/gnss_raw_stream-amd64-linux --help >/dev/null

FROM scratch AS artifact
COPY --from=build /app/dist/gnss_raw_stream-amd64-linux /gnss_raw_stream-amd64-linux
