FROM python:3.13-slim

RUN apt-get update && \
    apt-get install -y ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Copy your app into /app/discordbot (assuming Dockerfile is in parent of discordbot/)
COPY discordbot /app/discordbot

RUN mkdir -p /app/discordbot/data

WORKDIR /app/discordbot

ENV PYTHONUNBUFFERED=1
ENV PYTHONIOENCODING=UTF-8

CMD ["python", "main.py"]