from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from sqlalchemy.exc import IntegrityError as SAIntegrityError

from db.models.settings import AdGroupCache
from db.models.template import RdpTemplate, TemplateGroupBinding
from rdp.rdp_file import RDP_PARAM_SCHEMA, default_rdp_params
from redis_store.sessions import AdminWebSessionData
from services.admin.dependencies import get_db_sessionmaker, require_admin

router = APIRouter(prefix="/api/admin/templates", tags=["admin-templates"])


class TemplateOut(BaseModel):
    id: str
    name: str
    is_default: bool
    priority: int
    params: dict[str, Any]
    groups: list[str]
    group_details: list[dict[str, str]] = Field(default_factory=list)


class TemplateCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    is_default: bool = False
    priority: int = Field(default=0, ge=0)
    params: dict[str, Any] = Field(default_factory=dict)
    groups: list[str] = Field(default_factory=list)


class TemplateUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    is_default: bool | None = None
    priority: int | None = Field(default=None, ge=0)
    params: dict[str, Any] | None = None
    groups: list[str] | None = None


async def _db(request: Request) -> AsyncSession:
    return get_db_sessionmaker(request)()


def _group_uuids(groups: list[str]) -> list[uuid.UUID]:
    out: list[uuid.UUID] = []
    for g in groups:
        try:
            out.append(uuid.UUID(str(g)))
        except Exception:
            raise HTTPException(status_code=400, detail=f"Invalid group GUID: {g}") from None
    return out


async def _load_group_name_map(session: AsyncSession, templates: list[RdpTemplate]) -> dict[str, str]:
    guid_set: set[uuid.UUID] = set()
    for t in templates:
        for b in (t.group_bindings or []):
            guid_set.add(b.ad_group_guid)
    if not guid_set:
        return {}
    rows = await session.execute(sa.select(AdGroupCache.guid, AdGroupCache.cn).where(AdGroupCache.guid.in_(list(guid_set))))
    return {str(guid): str(cn) for guid, cn in rows.all()}


def _to_out(t: RdpTemplate, group_name_map: dict[str, str] | None = None) -> TemplateOut:
    name_map = group_name_map or {}
    group_guids = [str(g.ad_group_guid) for g in (t.group_bindings or [])]
    details = [{"guid": g, "cn": name_map.get(g, g)} for g in group_guids]
    return TemplateOut(
        id=str(t.id),
        name=t.name,
        is_default=bool(t.is_default),
        priority=int(t.priority),
        params=dict(t.params or {}),
        groups=group_guids,
        group_details=details,
    )


@router.get("/schema")
async def get_schema(_: AdminWebSessionData = Depends(require_admin)) -> dict[str, Any]:
    return RDP_PARAM_SCHEMA


@router.get("", response_model=list[TemplateOut])
async def list_templates(request: Request, _: AdminWebSessionData = Depends(require_admin)) -> list[TemplateOut]:
    session = await _db(request)
    try:
        rows = await session.execute(
            sa.select(RdpTemplate).options(selectinload(RdpTemplate.group_bindings)).order_by(RdpTemplate.is_default.desc(), RdpTemplate.priority, RdpTemplate.name)
        )
        templates = list(rows.scalars().all())
        gmap = await _load_group_name_map(session, templates)
        return [_to_out(v, gmap) for v in templates]
    finally:
        await session.close()


@router.post("", response_model=TemplateOut, status_code=status.HTTP_201_CREATED)
async def create_template(request: Request, body: TemplateCreate, _: AdminWebSessionData = Depends(require_admin)) -> TemplateOut:
    session = await _db(request)
    try:
        if body.is_default:
            await session.execute(sa.update(RdpTemplate).values(is_default=False))

        params = default_rdp_params()
        params.update(body.params or {})
        t = RdpTemplate(
            name=body.name.strip(),
            is_default=bool(body.is_default),
            priority=int(body.priority),
            params=params,
        )
        t.group_bindings = [TemplateGroupBinding(ad_group_guid=g) for g in _group_uuids(body.groups)]
        session.add(t)
        try:
            await session.commit()
        except SAIntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail=f"Шаблон с именем '{body.name.strip()}' уже существует")
        await session.refresh(t, attribute_names=["group_bindings"])
        gmap = await _load_group_name_map(session, [t])
        return _to_out(t, gmap)
    finally:
        await session.close()


@router.put("/{template_id}", response_model=TemplateOut)
async def update_template(
    request: Request, template_id: str, body: TemplateUpdate, _: AdminWebSessionData = Depends(require_admin)
) -> TemplateOut:
    try:
        tid = uuid.UUID(template_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid template id") from None

    session = await _db(request)
    try:
        row = await session.execute(
            sa.select(RdpTemplate).where(RdpTemplate.id == tid).options(selectinload(RdpTemplate.group_bindings))
        )
        t = row.scalars().first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")

        if body.is_default is True:
            await session.execute(sa.update(RdpTemplate).values(is_default=False))
            t.is_default = True
        elif body.is_default is False:
            t.is_default = False

        if body.name is not None:
            t.name = body.name.strip()
        if body.priority is not None:
            t.priority = int(body.priority)
        if body.params is not None:
            merged = default_rdp_params()
            merged.update(body.params)
            t.params = merged
        if body.groups is not None:
            t.group_bindings = [TemplateGroupBinding(ad_group_guid=g) for g in _group_uuids(body.groups)]

        try:
            await session.commit()
        except SAIntegrityError:
            await session.rollback()
            raise HTTPException(status_code=409, detail=f"Шаблон с таким именем уже существует")
        await session.refresh(t, attribute_names=["group_bindings"])
        gmap = await _load_group_name_map(session, [t])
        return _to_out(t, gmap)
    finally:
        await session.close()


@router.delete("/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_template(request: Request, template_id: str, _: AdminWebSessionData = Depends(require_admin)) -> None:
    try:
        tid = uuid.UUID(template_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid template id") from None

    session = await _db(request)
    try:
        row = await session.execute(sa.select(RdpTemplate).where(RdpTemplate.id == tid))
        t = row.scalars().first()
        if not t:
            raise HTTPException(status_code=404, detail="Template not found")
        if t.is_default:
            raise HTTPException(status_code=400, detail="Default template cannot be deleted")
        await session.delete(t)
        await session.commit()
    finally:
        await session.close()


@router.get("/preview")
async def preview_template(
    request: Request,
    groups: list[str] = [],
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, Any]:
    group_set = {str(v).strip().lower() for v in groups if str(v).strip()}
    session = await _db(request)
    try:
        rows = await session.execute(sa.select(RdpTemplate).options(selectinload(RdpTemplate.group_bindings)))
        templates = list(rows.scalars().all())
        default_tpl = next((x for x in templates if x.is_default), None)
        merged = default_rdp_params()
        if default_tpl:
            merged.update(default_tpl.params or {})
        for t in sorted(templates, key=lambda x: int(x.priority)):
            if t.is_default:
                continue
            binds = {str(v.ad_group_guid).lower() for v in (t.group_bindings or [])}
            if binds and not binds.intersection(group_set):
                continue
            merged.update(t.params or {})
        return {"params": merged}
    finally:
        await session.close()
