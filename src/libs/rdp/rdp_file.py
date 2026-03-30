"""RDP file builder and parameter schema for template management."""

from __future__ import annotations

from typing import Any

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from db.models.template import RdpTemplate

RDP_PARAM_SCHEMA: dict[str, Any] = {
    "display": {
        "label": "Настройка отображения",
        "params": {
            "screen mode id": {"label": "Режим экрана", "type": "select", "options": [{"value": 1, "label": "Оконный режим"}, {"value": 2, "label": "Полный экран"}], "default": 2, "ui_hidden": True},
            "desktopwidth": {"label": "Ширина", "type": "number", "min": 640, "max": 7680, "default": 1920, "ui_hidden": True},
            "desktopheight": {"label": "Высота", "type": "number", "min": 480, "max": 4320, "default": 1080, "ui_hidden": True},
            "session bpp": {"label": "Глубина цвета", "type": "select", "options": [{"value": 15, "label": "High color (15 bit)"}, {"value": 16, "label": "High color (16 bit)"}, {"value": 24, "label": "True color (24 bit)"}, {"value": 32, "label": "Наивысшее качество (32 бит)"}], "default": 32, "ui_hidden": True},
            "use multimon": {"label": "Использовать все мои мониторы", "type": "toggle", "default": 0, "ui_hidden": True},
        },
    },
    "local_resources": {
        "label": "Локальные ресурсы",
        "params": {
            "audiomode": {"label": "Воспроизведение звука", "type": "select", "options": [{"value": 0, "label": "На локальном ПК"}, {"value": 1, "label": "Не воспроизводить"}, {"value": 2, "label": "На удаленном ПК"}], "default": 0},
            "audiocapturemode": {"label": "Запись звука", "type": "toggle", "default": 0},
            "keyboardhook": {"label": "Сочетания клавиш Windows", "type": "select", "options": [{"value": 0, "label": "Локально"}, {"value": 1, "label": "Удаленно"}, {"value": 2, "label": "Только fullscreen"}], "default": 2},
            "redirectclipboard": {"label": "Буфер обмена", "type": "toggle", "default": 1},
            "redirectprinters": {"label": "Принтеры", "type": "toggle", "default": 1},
            "redirectdrives": {"label": "Диски", "type": "toggle", "default": 1},
            "redirectsmartcards": {"label": "Смарт-карты", "type": "toggle", "default": 1},
        },
    },
    "experience": {
        "label": "Взаимодействие",
        "params": {
            "disable wallpaper": {"label": "Отключить обои", "type": "toggle", "default": 0},
            "allow font smoothing": {"label": "Сглаживание шрифтов", "type": "toggle", "default": 1},
            "allow desktop composition": {"label": "Композиция рабочего стола", "type": "toggle", "default": 1},
            "bitmapcachepersistenable": {"label": "Постоянный bitmap cache", "type": "toggle", "default": 1},
            "autoreconnection enabled": {"label": "Автопереподключение", "type": "toggle", "default": 1},
        },
    },
}

SYSTEM_KEYS = {"full address", "loadbalanceinfo", "negotiate security layer", "enablecredsspsupport", "authentication level"}


def default_rdp_params() -> dict[str, int]:
    out: dict[str, int] = {}
    for section in RDP_PARAM_SCHEMA.values():
        for key, meta in section["params"].items():
            out[key] = int(meta.get("default", 0))
    return out


def _to_line(key: str, value: Any) -> str:
    if isinstance(value, bool):
        return f"{key}:i:{1 if value else 0}"
    if isinstance(value, int):
        return f"{key}:i:{value}"
    if isinstance(value, float):
        return f"{key}:i:{int(value)}"
    return f"{key}:s:{value}"


async def build_rdp_content(
    *, db_session: AsyncSession | None, user_group_guids: list[str],
    proxy_host: str, proxy_port: int, token: str,
) -> str:
    """Build complete .rdp file content with template merging."""
    merged: dict[str, Any] = default_rdp_params()
    if db_session is not None:
        rows = await db_session.execute(sa.select(RdpTemplate).options(selectinload(RdpTemplate.group_bindings)))
        templates = list(rows.scalars().all())
        default_tpl = next((x for x in templates if x.is_default), None)
        if default_tpl:
            merged.update(default_tpl.params or {})
        group_set = {str(v).strip().lower() for v in user_group_guids if str(v).strip()}
        for t in sorted(templates, key=lambda x: int(x.priority)):
            if t.is_default:
                continue
            binds = {str(b.ad_group_guid).lower() for b in (t.group_bindings or [])}
            if binds and not binds.intersection(group_set):
                continue
            merged.update(t.params or {})
    merged["networkautodetect"] = 1
    merged["bandwidthautodetect"] = 1
    merged["full address"] = f"{proxy_host}:{proxy_port}"
    merged["loadbalanceinfo"] = token
    merged["negotiate security layer"] = 1
    merged["enablecredsspsupport"] = 0
    merged["authentication level"] = 2
    lines = [_to_line(k, v) for k, v in merged.items()]
    return "\n".join(lines) + "\n"
