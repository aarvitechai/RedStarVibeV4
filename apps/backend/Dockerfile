# One backend image; the process type (api, worker, beat, migrate) is chosen by the compose command.
FROM python:3.15-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app

FROM base AS deps
COPY pyproject.toml ./
RUN mkdir app && touch app/__init__.py && pip install --prefix=/install ".[dev]"

FROM base AS runtime
# OS security updates, licensed (OFL) Latin + Devanagari fonts for cards/share images, ffmpeg for media.
RUN apt-get update && apt-get upgrade -y && apt-get install -y --no-install-recommends fonts-noto-core ffmpeg && rm -rf /var/lib/apt/lists/*
RUN groupadd --system rsv && useradd --system --gid rsv --home /app rsv
COPY --from=deps /install /usr/local
COPY . .
USER rsv
EXPOSE 8000
CMD ["gunicorn", "app.main:app", "-k", "uvicorn.workers.UvicornWorker", "-b", "0.0.0.0:8000", "-w", "2", "--graceful-timeout", "30", "--no-control-socket"]
