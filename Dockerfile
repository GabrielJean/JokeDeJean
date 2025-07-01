# Build stage
FROM python:3.13-slim AS build

RUN apt-get update && apt-get install -y git ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --prefix=/install --no-cache-dir -r requirements.txt
COPY discordbot /app/discordbot

# Production image
FROM python:3.13-slim

RUN apt-get update && apt-get install -y ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY --from=build /install /usr/local
COPY --from=build /app/discordbot /app/discordbot
RUN mkdir -p /app/discordbot/data

WORKDIR /app/discordbot

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8
CMD ["python", "main.py"]