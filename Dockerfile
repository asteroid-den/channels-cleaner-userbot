# syntax=docker/dockerfile:1

# --- the web UI -------------------------------------------------------------------------------
# Static files are the same for every platform, so build them natively: npm under QEMU (arm64
# on an amd64 runner) takes ages or hangs.
FROM --platform=$BUILDPLATFORM node:22-alpine AS ui
WORKDIR /src/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
# vite writes to ../src/channels_cleaner/static
RUN mkdir -p ../src/channels_cleaner && npm run build

# --- dependencies + app in a venv (uv stays in this stage) ------------------------------------
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock README.md LICENSE ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY src ./src
COPY --from=ui /src/src/channels_cleaner/static ./src/channels_cleaner/static
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

# --- runtime ----------------------------------------------------------------------------------
FROM python:3.12-slim
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
CMD ["channels-cleaner"]
