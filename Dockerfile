# ── Stage 1: base with FFmpeg + Python ────────────────────────
FROM python:3.11-slim AS base

# Install FFmpeg and system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
	ffmpeg \
	fonts-dejavu-core \
	curl \
	&& rm -rf /var/lib/apt/lists/*

WORKDIR /app

# ── Stage 2: install Python deps ──────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ── Stage 3: copy app code ────────────────────────────────────
COPY *.py ./
COPY *.html ./
COPY core ./core

# Create persistent directories (mounted as volumes)
RUN mkdir -p audio images output data branding

# ── Runtime ───────────────────────────────────────────────────
# Run dashboard server.
CMD ["python", "server.py"]

# ── Build & run ───────────────────────────────────────────────
# docker build -t yt-automation .
# docker run -d --env-file .env #   -v $(pwd)/data:/app/data #   -v $(pwd)/client_secrets.json:/app/client_secrets.json:ro #   --name ytbot yt-automation
#
# View logs:    docker logs -f ytbot
# Stop:         docker stop ytbot
# Shell access: docker exec -it ytbot bash