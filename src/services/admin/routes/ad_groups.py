from __future__ import annotations

import hashlib
import json
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.settings import AdGroupCache
from identity.ldap_auth import LDAPAuthenticator
from redis_store.sessions import AdminWebSessionData, SessionStore
from services.admin.dependencies import get_db_sessionmaker, get_session_store, require_admin

router = APIRouter(prefix="/api/admin/ad-groups", tags=["admin-ad-groups"])


class AdGroupOut(BaseModel):
    guid: str
    dn: str
    cn: str
    description: str | None = None


class RefreshResult(BaseModel):
    imported: int = Field(ge=0)


def _get_redis(request: Request) -> SessionStore:
    return get_session_store(request)


def _get_ldap(request: Request) -> LDAPAuthenticator:
    ldap = getattr(request.app.state, "ldap_auth", None)
    if ldap is None:
        raise HTTPException(status_code=500, detail="LDAP is not initialized")
    return ldap


async def _upsert_groups(session: AsyncSession, groups: list[dict[str, Any]]) -> None:
    if not groups:
        return
    rows = []
    for g in groups:
        if not g.get("guid") or not g.get("dn") or not g.get("cn"):
            continue
        rows.append(
            {
                "guid": g["guid"],
                "dn": g["dn"],
                "cn": g["cn"],
                "description": g.get("description"),
            }
        )
    if not rows:
        return

    stmt = pg_insert(AdGroupCache).values(rows)
    stmt = stmt.on_conflict_do_update(
        index_elements=[AdGroupCache.guid],
        set_={
            "dn": stmt.excluded.dn,
            "cn": stmt.excluded.cn,
            "description": stmt.excluded.description,
            "cached_at": sa.func.now(),
        },
    )
    await session.execute(stmt)


@router.get("", response_model=list[AdGroupOut])
async def search_groups(
    request: Request,
    search: str = "",
    limit: int = 20,
    _: AdminWebSessionData = Depends(require_admin),
) -> list[AdGroupOut]:
    q = (search or "").strip()
    if len(q) < 2:
        return []

    limit = max(1, min(int(limit or 20), 50))

    redis_store = _get_redis(request)
    cache_key = "rdp:adgroups:search:" + hashlib.sha1(q.lower().encode("utf-8")).hexdigest()
    cached = redis_store.client.get(cache_key)
    if cached:
        try:
            items = json.loads(cached)
            return [AdGroupOut(**v) for v in items]
        except Exception:
            redis_store.client.delete(cache_key)

    ldap = _get_ldap(request)
    groups = ldap.search_groups(q, limit=limit)

    # Cache short-lived search results.
    redis_store.client.setex(cache_key, 120, json.dumps(groups, ensure_ascii=False))

    # Upsert into PostgreSQL for display and joins.
    factory = get_db_sessionmaker(request)
    async with factory() as session:
        await _upsert_groups(session, groups)
        await session.commit()

    return [AdGroupOut(**v) for v in groups]


@router.post("/refresh", response_model=RefreshResult)
async def refresh_groups(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> RefreshResult:
    ldap = _get_ldap(request)
    groups = ldap.list_groups(limit=20000)

    factory = get_db_sessionmaker(request)
    async with factory() as session:
        await _upsert_groups(session, groups)
        await session.commit()

    return RefreshResult(imported=len(groups))
