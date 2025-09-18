# Build dependencies only once, cache pip, minimize layers

# 1. Use a specific tag for stability, and leverage pip cache
FROM python:3.13-slim AS build

RUN apt-get update && apt-get install -y git ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app

# Only copy requirements to cache dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --prefix=/install --no-cache-dir -r requirements.txt

# Only copy source after installing requirements (better cache)
COPY discordbot /app/discordbot
COPY discordbot/Audio /app/Audio

# 2. Final image: only what's needed for runtime
FROM python:3.13-slim

# Install only runtime dependencies
RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy Python deps installed in build (faster than re-installing)
COPY --from=build /install /usr/local

# Copy source
COPY --from=build /app/discordbot /app/discordbot
COPY --from=build /app/Audio /app/Audio

# Minimize layers: create dir while copying if possible
RUN mkdir -p /app/discordbot/data

WORKDIR /app/discordbot

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

CMD ["python3", "-m", "discordbot.run_both"]