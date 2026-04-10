"""Cert-manager sidecar: listens for domain change signals via Redis pub/sub
and runs certbot to issue a new Let's Encrypt certificate."""

from __future__ import annotations

import logging
import os
import shlex
import signal
import subprocess
import time

import redis

from common.logging import setup_logging
from config.loader import load_config
from redis_store import keys

logger = logging.getLogger("rdpproxy.cert-manager")

CHANGE_DOMAIN_SCRIPT = "/app/deploy/scripts/change-domain.sh"

_running = True


def _handle_signal(signum: int, _frame: object) -> None:
    global _running
    logger.info("Received signal %d, shutting down", signum)
    _running = False


def _run_certbot(domain: str) -> bool:
    """Execute the change-domain script and return True on success."""
    cmd = [CHANGE_DOMAIN_SCRIPT, domain]
    logger.info("Running: %s", shlex.join(cmd))
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.stdout:
            for line in result.stdout.strip().splitlines():
                logger.info("  stdout: %s", line)
        if result.stderr:
            for line in result.stderr.strip().splitlines():
                logger.warning("  stderr: %s", line)
        if result.returncode == 0:
            logger.info("Certificate issued successfully for %s", domain)
            return True
        logger.error("certbot exited with code %d for %s", result.returncode, domain)
        return False
    except subprocess.TimeoutExpired:
        logger.error("certbot timed out for %s", domain)
        return False
    except Exception:
        logger.exception("Failed to run certbot for %s", domain)
        return False


def _read_public_port() -> str:
    """Read PUBLIC_PORT from the mounted .env file."""
    try:
        with open("/app/.env", "r") as f:
            for line in f:
                if line.startswith("PUBLIC_PORT="):
                    return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return "443"


def _recreate_haproxy() -> None:
    """Recreate only the haproxy container with the new PUBLIC_PORT.

    --project-directory is set to the HOST path so that relative bind-mount
    paths (e.g. ./deploy/haproxy) resolve correctly on the Docker daemon side.
    --no-deps prevents cascading recreation of admin/portal/relay.
    --force-recreate ensures the container picks up the new port mapping.
    """
    public_port = _read_public_port()
    compose_file = os.environ.get("COMPOSE_FILE", "/app/docker-compose.yml")
    project = os.environ.get("COMPOSE_PROJECT", "rdpproxy")
    host_dir = os.environ.get("HOST_PROJECT_DIR", "/opt/rdpproxy")

    cmd = [
        "docker", "compose",
        "-f", compose_file,
        "-p", project,
        "--project-directory", host_dir,
        "--env-file", "/app/.env",
        "up", "-d", "--no-deps", "--no-build", "--force-recreate", "haproxy",
    ]

    env = os.environ.copy()
    env["PUBLIC_PORT"] = public_port

    logger.info("Recreating haproxy with PUBLIC_PORT=%s: %s", public_port, shlex.join(cmd))
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=60, env=env)
        for line in (result.stderr or "").strip().splitlines():
            logger.info("  compose: %s", line)
        if result.returncode == 0:
            logger.info("haproxy recreated successfully on port %s", public_port)
        else:
            logger.error("docker compose exited with code %d", result.returncode)
    except subprocess.TimeoutExpired:
        logger.error("docker compose timed out while recreating haproxy")
    except Exception:
        logger.exception("Failed to recreate haproxy")


def main() -> None:
    setup_logging(service="cert-manager")
    config = load_config()

    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)

    logger.info(
        "cert-manager starting, subscribing to %s, %s",
        keys.CERT_RENEW_CHANNEL,
        keys.HAPROXY_RECREATE_CHANNEL,
    )

    while _running:
        try:
            rc = redis.Redis(
                host=config.redis.host,
                port=config.redis.port,
                password=config.redis.password or None,
                db=config.redis.db,
                decode_responses=True,
            )
            rc.ping()
            logger.info("Connected to Redis")

            pubsub = rc.pubsub()
            pubsub.subscribe(keys.CERT_RENEW_CHANNEL, keys.HAPROXY_RECREATE_CHANNEL)

            while _running:
                msg = pubsub.get_message(ignore_subscribe_messages=True, timeout=2.0)
                if msg is None:
                    continue
                if msg["type"] != "message":
                    continue

                channel = msg.get("channel") or ""
                if channel == keys.HAPROXY_RECREATE_CHANNEL:
                    logger.info("Received HAProxy recreate signal (public port / compose)")
                    _recreate_haproxy()
                    continue

                domain = (msg.get("data") or "").strip()
                if not domain:
                    logger.warning("Received empty domain, skipping")
                    continue

                logger.info("Received cert renew request for domain: %s", domain)
                _run_certbot(domain)

        except redis.ConnectionError:
            logger.warning("Redis connection lost, reconnecting in 5s...")
            time.sleep(5)
        except Exception:
            logger.exception("Unexpected error, restarting in 5s...")
            time.sleep(5)


if __name__ == "__main__":
    main()
