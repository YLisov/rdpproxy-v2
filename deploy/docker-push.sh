#!/usr/bin/env bash
# Сборка и публикация образа dc319/rdpproxy на Docker Hub.
# Использование (из корня репозитория, после docker login):
#   ./deploy/docker-push.sh              # тег по умолчанию 0.1.0-b1
#   ./deploy/docker-push.sh 0.2.0        # произвольный тег
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
TAG="${1:-0.1.0-b1}"
IMAGE="dc319/rdpproxy:${TAG}"

cd "$ROOT"
LATEST="dc319/rdpproxy:latest"

echo "Building ${IMAGE} ..."
docker build -t "$IMAGE" -t "$LATEST" .
echo "Pushing ${IMAGE} ..."
docker push "$IMAGE"
echo "Pushing ${LATEST} ..."
docker push "$LATEST"
echo "Done — published ${IMAGE} + ${LATEST}"
