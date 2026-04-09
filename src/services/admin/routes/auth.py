"""Admin authentication routes: login, logout, change-password (HTML forms)."""

from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from db.models.admin_user import AdminUser
from redis_store.sessions import AdminWebSessionData
from security.login_limiter import admin_limiter
from security.passwords import hash_password, verify_password
from services.admin.dependencies import (
    ADMIN_COOKIE_NAME,
    ADMIN_CSRF_COOKIE_NAME,
    browser_fingerprint,
    get_client_ip,
    get_config,
    get_db_sessionmaker,
    get_redis_client,
    get_session_store,
    require_admin,
)

router = APIRouter()
logger = logging.getLogger("rdpproxy.admin.auth")


def _issue_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def _ensure_csrf_token(request: Request) -> str:
    return request.cookies.get(ADMIN_CSRF_COOKIE_NAME) or _issue_csrf_token()


async def _render_login_page(request: Request, error: str | None, status_code: int = 200) -> HTMLResponse:
    templates = request.app.state.templates
    csrf_token = _ensure_csrf_token(request)
    loader = getattr(request.app.state, "load_portal_name", None)
    portal_name = (await loader()) if loader else "RDP Proxy"
    response = templates.TemplateResponse(
        request, "admin_login.html",
        {"error": error, "csrf_token": csrf_token, "portal_name": portal_name},
        status_code=status_code,
    )
    cfg_obj = getattr(request.app.state, "config", None)
    secure_flag = cfg_obj.admin.secure_cookies if cfg_obj else False
    response.set_cookie(key=ADMIN_CSRF_COOKIE_NAME, value=csrf_token, httponly=False, secure=secure_flag, samesite="lax", max_age=600)
    return response


@router.get("/login", response_class=HTMLResponse)
async def login_page(request: Request) -> HTMLResponse:
    store = get_session_store(request)
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    if sid:
        sess = store.get_admin_web_session(sid, browser_fingerprint=browser_fingerprint(request))
        if sess and not sess.must_change_password:
            return RedirectResponse(url="/admin/dashboard", status_code=303)
    return await _render_login_page(request, error=None)


@router.post("/login", response_class=HTMLResponse)
async def login_submit(
    request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(""),
) -> HTMLResponse:
    csrf_cookie = request.cookies.get(ADMIN_CSRF_COOKIE_NAME, "")
    if not csrf_cookie or csrf_cookie != csrf_token:
        return await _render_login_page(request, error="Сессия формы истекла. Обновите страницу.", status_code=400)

    rc = get_redis_client(request)
    limiter = admin_limiter(rc)
    ip = get_client_ip(request)

    if limiter.is_locked(ip, username):
        return await _render_login_page(request, error="Слишком много попыток входа. Попробуйте позже.", status_code=429)

    factory = get_db_sessionmaker(request)
    store = get_session_store(request)
    cfg = get_config(request)
    uname = username.strip()
    async with factory() as dbs:
        row = await dbs.execute(sa.select(AdminUser).where(sa.func.lower(AdminUser.username) == uname.lower()))
        user = row.scalars().first()
        if user is None or not user.is_active or not verify_password(user.password_hash, password):
            limiter.record_failure(
                ip, username,
                max_attempts=cfg.security.login_attempts_per_minute,
                lock_seconds=cfg.security.login_lock_seconds,
            )
            return await _render_login_page(request, error="Неверный логин или пароль.", status_code=401)
        user.last_login_at = datetime.now(timezone.utc)
        await dbs.commit()
        admin_id = str(user.id)
        admin_name = user.username
        must_change = bool(user.must_change_password)
        user_allowed_ips = list(user.allowed_ips or [])

    limiter.clear(ip, username)
    web_session_id = store.create_admin_web_session(
        admin_user_id=admin_id, username=admin_name,
        must_change_password=must_change, browser_fingerprint=browser_fingerprint(request),
        allowed_ips=user_allowed_ips,
    )
    secure_flag = cfg.admin.secure_cookies
    response = RedirectResponse(url="/admin/change-password" if must_change else "/admin/dashboard", status_code=303)
    response.set_cookie(
        key=ADMIN_COOKIE_NAME, value=web_session_id, httponly=True, secure=secure_flag,
        samesite="lax", max_age=cfg.redis.web_session_ttl,
    )
    response.set_cookie(key=ADMIN_CSRF_COOKIE_NAME, value=_issue_csrf_token(), httponly=False, secure=secure_flag, samesite="lax", max_age=600)
    return response


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    sid = request.cookies.get(ADMIN_COOKIE_NAME)
    store = get_session_store(request)
    if sid:
        store.delete_admin_web_session(sid)
    response = RedirectResponse(url="/admin/login", status_code=303)
    response.delete_cookie(ADMIN_COOKIE_NAME)
    response.delete_cookie(ADMIN_CSRF_COOKIE_NAME)
    return response


@router.get("/change-password", response_class=HTMLResponse)
async def change_password_page(request: Request, admin: AdminWebSessionData = Depends(require_admin)) -> HTMLResponse:
    templates = request.app.state.templates
    csrf_token = _ensure_csrf_token(request)
    response = templates.TemplateResponse(
        request, "admin_change_password.html",
        {"admin": admin, "error": None, "csrf_token": csrf_token},
    )
    cfg_obj = getattr(request.app.state, "config", None)
    secure_flag = cfg_obj.admin.secure_cookies if cfg_obj else False
    response.set_cookie(key=ADMIN_CSRF_COOKIE_NAME, value=csrf_token, httponly=False, secure=secure_flag, samesite="lax", max_age=600)
    return response


@router.post("/change-password", response_class=HTMLResponse)
async def change_password_submit(
    request: Request, current_password: str = Form(...), new_password: str = Form(...),
    new_password2: str = Form(...), csrf_token: str = Form(""),
    admin: AdminWebSessionData = Depends(require_admin),
) -> HTMLResponse:
    templates_engine = request.app.state.templates
    csrf_cookie = request.cookies.get(ADMIN_CSRF_COOKIE_NAME, "")
    ctx = {"admin": admin, "csrf_token": _ensure_csrf_token(request)}
    if not csrf_cookie or csrf_cookie != csrf_token:
        return templates_engine.TemplateResponse(request, "admin_change_password.html", {**ctx, "error": "Сессия формы истекла."}, status_code=400)
    if new_password != new_password2:
        return templates_engine.TemplateResponse(request, "admin_change_password.html", {**ctx, "error": "Новые пароли не совпадают."}, status_code=400)
    if len(new_password) < 8:
        return templates_engine.TemplateResponse(request, "admin_change_password.html", {**ctx, "error": "Пароль должен быть не короче 8 символов."}, status_code=400)

    factory = get_db_sessionmaker(request)
    store = get_session_store(request)
    async with factory() as dbs:
        user = await dbs.get(AdminUser, uuid.UUID(admin.admin_user_id))
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        if not verify_password(user.password_hash, current_password):
            return templates_engine.TemplateResponse(request, "admin_change_password.html", {**ctx, "error": "Неверный текущий пароль."}, status_code=401)
        user.password_hash = hash_password(new_password)
        user.must_change_password = False
        await dbs.commit()
    store.update_admin_must_change(admin.session_id, False)
    return RedirectResponse(url="/admin/dashboard", status_code=303)
