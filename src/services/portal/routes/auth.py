"""Portal authentication routes: login, logout."""

from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Form, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse

from security.login_limiter import portal_limiter
from services.portal.dependencies import (
    COOKIE_NAME,
    CSRF_COOKIE_NAME,
    browser_fingerprint,
    get_client_ip,
    get_config,
    get_ldap,
    get_portal_name,
    get_redis_client,
    get_session_store,
    get_settings_manager,
    is_ldap_configured,
)

router = APIRouter()
logger = logging.getLogger("rdpproxy.portal.auth")


def _issue_csrf_token() -> str:
    return secrets.token_urlsafe(24)


def _ensure_csrf_token(request: Request) -> str:
    return request.cookies.get(CSRF_COOKIE_NAME) or _issue_csrf_token()


async def _render_login_page(request: Request, error: str | None, status_code: int = 200) -> HTMLResponse:
    templates = request.app.state.templates
    csrf_token = _ensure_csrf_token(request)
    portal_name = await get_portal_name(request)
    response = templates.TemplateResponse(
        request, "login.html",
        {"session": None, "servers": [], "error": error, "csrf_token": csrf_token, "portal_name": portal_name},
        status_code=status_code,
    )
    cfg = get_config(request)
    secure_flag = cfg.proxy.secure_cookies
    response.set_cookie(key=CSRF_COOKIE_NAME, value=csrf_token, httponly=False, secure=secure_flag, samesite="lax", max_age=600)
    return response


@router.post("/login", response_class=HTMLResponse)
async def login(
    request: Request, username: str = Form(...), password: str = Form(...), csrf_token: str = Form(""),
) -> HTMLResponse:
    csrf_cookie = request.cookies.get(CSRF_COOKIE_NAME, "")
    if not csrf_cookie or csrf_cookie != csrf_token:
        return await _render_login_page(
            request,
            error="Сессия формы истекла. Обновите страницу и попробуйте снова.",
            status_code=400,
        )

    rc = get_redis_client(request)
    limiter = portal_limiter(rc)
    ip = get_client_ip(request)

    if limiter.is_locked(ip, username):
        return await _render_login_page(request, error="Слишком много попыток входа. Попробуйте позже.", status_code=429)

    if not is_ldap_configured(request):
        return await _render_login_page(
            request,
            error="Система не настроена. Обратитесь к администратору для настройки LDAP.",
            status_code=503,
        )

    ldap = get_ldap(request)
    try:
        user_info = ldap.authenticate(username=username.strip(), password=password)
    except Exception as exc:
        logger.warning("Login failed for username=%r: %s", username, exc)
        mgr = get_settings_manager(request)
        sec = mgr.security_params
        limiter.record_failure(
            ip, username,
            max_attempts=sec["login_attempts_per_minute"],
            lock_seconds=sec["login_lock_seconds"],
        )
        return await _render_login_page(request, error="Неверный логин или пароль.", status_code=401)

    store = get_session_store(request)
    limiter.clear(ip, username)
    mgr = get_settings_manager(request)
    web_session_id = store.create_web_session(
        username=user_info.username, password=password,
        groups=user_info.groups, group_guids=user_info.group_guids,
        browser_fingerprint=browser_fingerprint(request),
    )
    ttl = mgr.redis_ttl
    cfg = get_config(request)
    secure_flag = cfg.proxy.secure_cookies
    response = RedirectResponse(url="/", status_code=303)
    response.set_cookie(
        key=COOKIE_NAME, value=web_session_id, httponly=True, secure=secure_flag,
        samesite="lax", max_age=ttl.get("web_session_ttl", 28800),
    )
    response.set_cookie(key=CSRF_COOKIE_NAME, value=_issue_csrf_token(), httponly=False, secure=secure_flag, samesite="lax", max_age=600)
    return response


@router.get("/logout")
async def logout(request: Request) -> RedirectResponse:
    session_id = request.cookies.get(COOKIE_NAME)
    store = get_session_store(request)
    if session_id:
        store.delete_web_session(session_id)
    response = RedirectResponse(url="/", status_code=303)
    response.delete_cookie(COOKIE_NAME)
    response.delete_cookie(CSRF_COOKIE_NAME)
    return response
