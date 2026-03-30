FROM python:3.12-slim AS base

RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY src/ ./src/
COPY assets/ ./assets/
COPY alembic.ini .

ENV PYTHONPATH=/app/src/libs:/app/src
ENV PYTHONUNBUFFERED=1
