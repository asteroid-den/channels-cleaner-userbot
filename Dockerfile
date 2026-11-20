# syntax=docker/dockerfile:1

# Base images pinned to a release and its digest: a rebuild gets the same Python and Node, not whatever the floating
# tag points at that day. To move on: docker buildx imagetools inspect <image>:<new tag> for the digest, then bump both
# Python stages together.

# --- the web UI -------------------------------------------------------------------------------
# Static files are the same for every platform, so build them natively: npm under QEMU (arm64
# on an amd64 runner) takes ages or hangs.
FROM --platform=$BUILDPLATFORM node:22.23.5-alpine@sha256:1314fb30ec37592d5845e5a160d522c0e680972aa534549940b8d73bde88481a AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite writes to ../src/channels_cleaner/static
RUN mkdir -p ../src/channels_cleaner && npm run build

# --- dependencies + app in a venv (uv stays in this stage) ------------------------------------
FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY --from=ui /src/src/channels_cleaner/static ./src/channels_cleaner/static
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

# --- runtime ----------------------------------------------------------------------------------
FROM python:3.12.16-slim-trixie@sha256:5e2bdb1b0d542d5039cffb8181c65930093949194a65c365dfb1b0fe13a4fa5b
WORKDIR /app
COPY --from=build /app/.venv /app/.venv

RUN useradd --create-home --uid 1000 cleaner && mkdir /data && chown cleaner /data
USER cleaner

# Listen on all interfaces inside the container; publish the port on 127.0.0.1 only
# (see compose.yaml) — anyone who reaches it controls your Telegram account.
ENV PATH=/app/.venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    CC_HOST=0.0.0.0 \
    CC_DATA_DIR=/data \
    CC_NO_BROWSER=1
VOLUME /data
EXPOSE 8765
# The app's own check: it answers /api/health once the server is up. start-period covers the first start's migrations
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD ["python", "-m", "channels_cleaner.healthcheck"]
CMD ["telegram-channels-cleaner"]
