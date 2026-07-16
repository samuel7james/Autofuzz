# AutoFuzz application image - multi-stage: build a wheel in a full Python
# image, then install just the wheel (not the build toolchain or source
# tree) into a slim runtime image.
#
# Build from the repo root:
#   docker build -f docker/Dockerfile -t autofuzz .
#
# Run a scan (mount a profile and a place to write the report):
#   docker run --rm \
#     -v "$(pwd)/examples/configs:/home/autofuzz/configs:ro" \
#     -v "$(pwd)/reports:/home/autofuzz/reports" \
#     -w /home/autofuzz/reports \
#     autofuzz web https://target.example --profile /home/autofuzz/configs/web-default.yaml
#
# See docker/docker-compose.yml for a ready-made local dev/lab setup
# (this image plus the disposable FTP fuzzing target).

# syntax=docker/dockerfile:1

FROM python:3.12-slim AS builder

WORKDIR /build

COPY pyproject.toml readme.md ./
COPY src ./src

RUN pip install --no-cache-dir build && \
    python -m build --wheel


FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

# Non-root by default: this image only ever runs the autofuzz CLI against
# targets the operator has already confirmed authorization for, and there
# is no reason for that process to run as root.
RUN useradd --create-home --uid 1000 --shell /bin/bash autofuzz

COPY --from=builder /build/dist/*.whl /tmp/
RUN pip install /tmp/*.whl && rm -rf /tmp/*.whl

# Pre-create and own the directories docker-compose.yml mounts volumes
# over (~/.autofuzz for scan sessions, ~/reports for output). A fresh
# named volume mounted over a path that doesn't already exist in the
# image is created root-owned by default; since the container runs as
# the non-root `autofuzz` user below, session persistence (which chmods
# itself to 700/600 - see core/scan.py) would otherwise fail with a
# PermissionError the first time anything tried to write there.
RUN mkdir -p /home/autofuzz/.autofuzz /home/autofuzz/reports && \
    chown -R autofuzz:autofuzz /home/autofuzz

USER autofuzz
WORKDIR /home/autofuzz

ENTRYPOINT ["autofuzz"]
CMD ["--help"]
