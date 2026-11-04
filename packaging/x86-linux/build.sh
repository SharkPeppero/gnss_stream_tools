#!/usr/bin/env bash
# Create a self-contained 32-bit x86 Linux executable in dist/x86-linux/.
set -euo pipefail

project_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
output_dir="$project_root/dist/x86-linux"

if ! command -v docker >/dev/null 2>&1; then
    echo "Docker is required. Install Docker with Buildx, then rerun this script." >&2
    exit 1
fi

mkdir -p "$output_dir"
docker buildx build \
    --platform linux/386 \
    --target artifact \
    --output "type=local,dest=$output_dir" \
    -f "$project_root/packaging/x86-linux/Dockerfile" \
    "$project_root"

binary="$output_dir/gnss_raw_stream-x86-linux"
test -f "$binary"
file "$binary"
echo "Created: $binary"
