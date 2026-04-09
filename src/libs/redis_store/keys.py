"""Centralized Redis key patterns for the entire application."""

from __future__ import annotations

# ── RDP token sessions ──
TOKEN = "rdp:token:{token}"

# ── Web sessions (portal) ──
WEB_SESSION = "rdp:web:{session_id}"

# ── Admin web sessions ──
ADMIN_WEB_SESSION = "rdp:admin:web:{session_id}"

# ── Active relay connections ──
ACTIVE_SESSION = "rdp:active:{instance_id}:{connection_id}"
ACTIVE_SCAN = "rdp:active:*"

# ── Kill signals ──
KILL_SESSION = "rdp:kill:{connection_id}"

# ── Metrics ──
METRICS_LATEST = "rdp:metrics:{instance_id}:latest"
METRICS_SERIES = "rdp:metrics:{instance_id}:series"
HEARTBEAT = "rdp:heartbeat:{instance_id}"

# ── Cluster nodes ──
NODE = "rdp:node:{instance_id}"
NODE_SCAN = "rdp:node:*"

# ── Restart signal ──
SIGNAL_RESTART = "rdp:signal:restart"

# ── AD groups search cache ──
AD_GROUPS_SEARCH = "rdp:adgroups:search:{hash}"

# ── Portal login rate-limiting ──
PORTAL_FAIL_IP = "rdp:fail:ip:{ip}"
PORTAL_FAIL_USER = "rdp:fail:user:{username}"
PORTAL_LOCK_IP = "rdp:lock:ip:{ip}"
PORTAL_LOCK_USER = "rdp:lock:user:{username}"

# ── Admin login rate-limiting ──
ADMIN_FAIL_IP = "rdp:admin:fail:ip:{ip}"
ADMIN_FAIL_USER = "rdp:admin:fail:user:{username}"
ADMIN_LOCK_IP = "rdp:admin:lock:ip:{ip}"
ADMIN_LOCK_USER = "rdp:admin:lock:user:{username}"

# ── Pub/Sub channels ──
SETTINGS_CHANGED_CHANNEL = "rdp:settings:changed"
CERT_RENEW_CHANNEL = "rdp:cert:renew"

# ── Common TTLs ──
KILL_TTL = 60
AD_SEARCH_CACHE_TTL = 120
METRICS_LATEST_TTL = 120
SIGNAL_RESTART_TTL = 30
FAIL_COUNTER_TTL = 60
