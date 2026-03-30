# RDPProxy v2 — Microservice Architecture

RDP-to-RDP proxy with web portal, admin panel, and cluster support.

## Architecture

```
                        ┌──────────────┐
         Port 8443      │              │
  ──────────────────────►   HAProxy    │
  (RDP or HTTPS)        │  L4 mux     │
                        └───┬─────┬───┘
                  RDP(PP v2)│     │HTTPS(TLS term)
                ┌───────────┘     └────────────┐
                ▼                              ▼
        ┌──────────────┐              ┌──────────────┐
        │  RDP Relay   │              │   Portal     │
        │  :8002       │              │   :8001      │
        │  CredSSP+MCS │              │   Login/RDP  │
        └──────┬───────┘              └──────┬───────┘
               │                             │
        ┌──────┴─────────────────────────────┴───┐
        │         PostgreSQL  +  Redis           │
        └────────────────────────────────────────┘

  Port 9090 (LAN only)
  ──────────► HAProxy ──────► Admin Panel :9090
  
  Metrics collector (background) → Redis + PostgreSQL heartbeats
```

## Services

| Service      | Port | Description                                |
|-------------|------|--------------------------------------------|
| **portal**  | 8001 | Web portal: LDAP login, server list, .rdp  |
| **admin**   | 9090 | Admin panel: CRUD servers, sessions, users |
| **rdp-relay** | 8002 | RDP proxy: CredSSP, MCS patching, plugins |
| **metrics** | —    | System metrics + cluster heartbeat         |
| **haproxy** | 8443, 9090 | L4 mux, TLS termination, PP v2       |
| **postgres**| 5432 | Primary database                           |
| **redis**   | 6379 | Sessions, active connections, metrics      |

## Quick Start

```bash
# 1. Clone and configure
cd /opt/rdpproxy-v2
cp .env.example .env
# Edit .env: set DB_PASSWORD, LAN_IP

cp config.yaml.example config.yaml
# Edit config.yaml: LDAP, security.encryption_key, proxy paths

# 2. Generate dev certificate (production: use Let's Encrypt)
./deploy/scripts/gen-dev-cert.sh

# 3. Start all services
docker compose up -d

# 4. Run database migrations
docker compose run --rm -v "$(pwd)/src:/app/src" portal \
    alembic upgrade head

# 5. Verify
docker compose ps
curl -sk https://localhost:8443/health
curl http://<LAN_IP>:9090/admin/login
```

## Default Credentials

First admin user is created automatically on portal startup:
- Username: `admin`
- Password: `admin`
- **Change immediately** after first login.

## Plugin System (RDP Relay)

The RDP relay supports plugins for data transformation:

- **McsPatchPlugin** — patches MCS Connect-Initial for SSL↔HYBRID bridge
- **SessionMonitorPlugin** — tracks session activity and idle timeouts

Custom plugins implement `RdpPlugin` base class:

```python
from services.rdp_relay.plugins.base import RdpPlugin, SessionContext

class MyPlugin(RdpPlugin):
    name = "my_plugin"

    async def on_client_packet(self, data: bytes, ctx: SessionContext) -> bytes:
        # transform data
        return data
```

Register in `services/rdp_relay/main.py`:
```python
plugins = PluginRegistry([McsPatchPlugin(), SessionMonitorPlugin(), MyPlugin()])
```

## Backup

```bash
# Manual backup
./deploy/scripts/pg-backup.sh

# Cron (daily at 3:00 AM, keep 7 days)
echo "0 3 * * * /opt/rdpproxy-v2/deploy/scripts/pg-backup.sh" | crontab -
```

## Firewall (nftables)

```bash
sudo nft -f /opt/rdpproxy-v2/deploy/nftables/rules.nft
```

Opens port 8443 publicly, restricts 9090 to LAN only.

## Project Structure

```
rdpproxy-v2/
├── src/
│   ├── libs/                  # Shared libraries
│   │   ├── config/            # Pydantic config loader
│   │   ├── db/                # SQLAlchemy models, engine, migrations
│   │   ├── redis_store/       # Sessions, encryption, active tracker
│   │   ├── identity/          # LDAP authenticator
│   │   ├── rdp/               # TPKT, X.224, MCS, CredSSP
│   │   ├── proxy_protocol/    # PP v1/v2 parser
│   │   ├── security/          # Argon2, CSRF, rate limiter
│   │   └── common/            # Logging, DNS, health
│   └── services/
│       ├── portal/            # Web portal service
│       ├── admin/             # Admin panel service
│       ├── rdp_relay/         # RDP relay + plugin system
│       └── metrics/           # Metrics collector
├── deploy/
│   ├── haproxy/               # HAProxy config + certs
│   ├── nftables/              # Firewall rules
│   └── scripts/               # Utility scripts
├── docker-compose.yml
├── Dockerfile
├── config.yaml
└── requirements.txt
```

## Scaling

Add nodes by running `docker compose up -d` on additional servers
with the same `config.yaml` (unique `instance.id` per node).
All nodes share the same PostgreSQL and Redis.
HAProxy runs on each node; an external L4 balancer distributes
traffic across nodes.
