FROM python:3.12-slim

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        certbot ca-certificates curl && \
    rm -rf /var/lib/apt/lists/*

# Docker CLI (for `docker compose` to reload haproxy/relay via socket)
RUN curl -fsSL https://download.docker.com/linux/static/stable/x86_64/docker-27.5.1.tgz | \
    tar xz --strip-components=1 -C /usr/local/bin docker/docker && \
    mkdir -p /usr/local/lib/docker/cli-plugins && \
    curl -fsSL "https://github.com/docker/compose/releases/download/v2.32.4/docker-compose-linux-x86_64" \
        -o /usr/local/lib/docker/cli-plugins/docker-compose && \
    chmod +x /usr/local/lib/docker/cli-plugins/docker-compose

WORKDIR /app

RUN pip install --no-cache-dir redis pyyaml pydantic

COPY src/services/cert_manager/ ./src/services/cert_manager/
COPY src/libs/common/ ./src/libs/common/
COPY src/libs/config/ ./src/libs/config/
COPY src/libs/redis_store/ ./src/libs/redis_store/

ENV PYTHONPATH=/app/src/libs:/app/src
ENV PYTHONUNBUFFERED=1

CMD ["python", "-m", "services.cert_manager.main"]
