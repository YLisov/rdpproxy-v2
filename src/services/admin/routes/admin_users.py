from __future__ import annotations

import uuid

import sqlalchemy as sa
from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from db.models.admin_user import AdminUser
from redis_store.sessions import AdminWebSessionData
from security.passwords import hash_password
from services.admin.dependencies import get_db_sessionmaker, require_admin

router = APIRouter(prefix="/api/admin/admin-users", tags=["admin-admin-users"])


async def _db(request: Request) -> AsyncSession:
    return get_db_sessionmaker(request)()


class AdminUserOut(BaseModel):
    id: str
    username: str
    is_active: bool
    must_change_password: bool
    allowed_ips: list[str] = Field(default_factory=list)
    last_login_at: str | None = None


class AdminUserCreate(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=8, max_length=256)
    is_active: bool = True
    allowed_ips: list[str] = Field(default_factory=list)


class AdminUserUpdate(BaseModel):
    is_active: bool | None = None
    allowed_ips: list[str] | None = None


class AdminPasswordResetBody(BaseModel):
    new_password: str = Field(min_length=8, max_length=256)


def _to_out(u: AdminUser) -> AdminUserOut:
    ips = u.allowed_ips or []
    return AdminUserOut(
        id=str(u.id),
        username=u.username,
        is_active=bool(u.is_active),
        must_change_password=bool(u.must_change_password),
        allowed_ips=[str(x) for x in ips],
        last_login_at=u.last_login_at.isoformat() if u.last_login_at else None,
    )


@router.get("", response_model=list[AdminUserOut])
async def list_admin_users(
    request: Request,
    _: AdminWebSessionData = Depends(require_admin),
) -> list[AdminUserOut]:
    session = await _db(request)
    try:
        rows = await session.execute(sa.select(AdminUser).order_by(AdminUser.username))
        return [_to_out(u) for u in rows.scalars().all()]
    finally:
        await session.close()


@router.post("", response_model=AdminUserOut, status_code=status.HTTP_201_CREATED)
async def create_admin_user(
    request: Request,
    body: AdminUserCreate,
    _: AdminWebSessionData = Depends(require_admin),
) -> AdminUserOut:
    session = await _db(request)
    try:
        exists = await session.execute(
            sa.select(sa.func.count(AdminUser.id)).where(sa.func.lower(AdminUser.username) == body.username.strip().lower())
        )
        if int(exists.scalar() or 0) > 0:
            raise HTTPException(status_code=409, detail="Пользователь с таким логином уже есть")
        u = AdminUser(
            username=body.username.strip(),
            password_hash=hash_password(body.password),
            is_active=bool(body.is_active),
            must_change_password=False,
            allowed_ips=list(body.allowed_ips or []),
        )
        session.add(u)
        await session.commit()
        await session.refresh(u)
        return _to_out(u)
    finally:
        await session.close()


@router.put("/{user_id}", response_model=AdminUserOut)
async def update_admin_user(
    request: Request,
    user_id: str,
    body: AdminUserUpdate,
    admin: AdminWebSessionData = Depends(require_admin),
) -> AdminUserOut:
    try:
        uid = uuid.UUID(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    session = await _db(request)
    try:
        u = await session.get(AdminUser, uid)
        if u is None:
            raise HTTPException(status_code=404, detail="Not found")

        if body.is_active is False and u.is_active:
            if str(uid) == admin.admin_user_id:
                raise HTTPException(status_code=400, detail="Нельзя отключить свою учётную запись")
            active_cnt = await session.scalar(
                sa.select(sa.func.count(AdminUser.id)).where(AdminUser.is_active == True)  # noqa: E712
            )
            if int(active_cnt or 0) <= 1:
                raise HTTPException(status_code=400, detail="Нельзя отключить последнего активного администратора")

        if body.is_active is not None:
            u.is_active = bool(body.is_active)
        if body.allowed_ips is not None:
            u.allowed_ips = list(body.allowed_ips)
        await session.commit()
        await session.refresh(u)
        return _to_out(u)
    finally:
        await session.close()


@router.post("/{user_id}/reset-password", response_model=dict[str, str])
async def reset_admin_password(
    request: Request,
    user_id: str,
    body: AdminPasswordResetBody,
    _: AdminWebSessionData = Depends(require_admin),
) -> dict[str, str]:
    try:
        uid = uuid.UUID(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    session = await _db(request)
    try:
        u = await session.get(AdminUser, uid)
        if u is None:
            raise HTTPException(status_code=404, detail="Not found")
        u.password_hash = hash_password(body.new_password)
        u.must_change_password = True
        await session.commit()
        return {"status": "ok"}
    finally:
        await session.close()


@router.delete("/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_admin_user(
    request: Request,
    user_id: str,
    admin: AdminWebSessionData = Depends(require_admin),
) -> None:
    try:
        uid = uuid.UUID(user_id)
    except Exception as exc:
        raise HTTPException(status_code=400, detail="Invalid user id") from exc

    if str(uid) == admin.admin_user_id:
        raise HTTPException(status_code=400, detail="Нельзя удалить свою учётную запись")

    session = await _db(request)
    try:
        u = await session.get(AdminUser, uid)
        if u is None:
            raise HTTPException(status_code=404, detail="Not found")
        if u.is_active:
            active_cnt = await session.scalar(
                sa.select(sa.func.count(AdminUser.id)).where(AdminUser.is_active == True)  # noqa: E712
            )
            if int(active_cnt or 0) <= 1:
                raise HTTPException(status_code=400, detail="Нельзя удалить последнего активного администратора")
        await session.delete(u)
        await session.commit()
    finally:
        await session.close()
