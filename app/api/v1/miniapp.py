from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.bot.storage import DriverLinkStore
from app.config import get_settings
from app.miniapp.auth import MiniAppAuthError, validate_telegram_init_data
from app.marketplace import (
    accept_marketplace_order,
    get_marketplace_order,
    get_marketplace_summary,
)
from app.marketplace.service import list_marketplace_orders
from app.services.fleet import FleetProviderError, get_fleet_provider

router = APIRouter(prefix="/api/v1/miniapp", tags=["miniapp"])


async def _resolve_driver_id(
    *,
    init_data: str | None,
    demo: bool,
) -> tuple[str, dict[str, Any] | None, bool]:
    settings = get_settings()

    if demo:
        if not (settings.YANDEX_MOCK_MODE and settings.TELEGRAM_MINI_APP_DEMO_MODE):
            raise HTTPException(status_code=403, detail="Demo mode is disabled.")
        return "driver-001", None, True

    if not settings.TELEGRAM_BOT_TOKEN:
        raise HTTPException(
            status_code=503,
            detail="Telegram bot token is not configured.",
        )

    try:
        telegram_user = validate_telegram_init_data(
            init_data or "",
            bot_token=settings.TELEGRAM_BOT_TOKEN,
        )
    except MiniAppAuthError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc

    store = DriverLinkStore(settings.TELEGRAM_BOT_DB_PATH)
    await store.init()
    driver_id = await store.get_driver_id(int(telegram_user["id"]))
    if not driver_id:
        raise HTTPException(
            status_code=403,
            detail="Telegram ещё не привязан к профилю водителя.",
        )

    return driver_id, telegram_user, False


@router.get("/bootstrap")
async def miniapp_bootstrap(
    demo: bool = Query(default=False),
    source: str | None = Query(default=None),
    status: str | None = Query(default=None),
    tariff: str | None = Query(default=None),
    x_telegram_init_data: str | None = Header(
        default=None,
        alias="X-Telegram-Init-Data",
    ),
) -> dict[str, Any]:
    settings = get_settings()
    driver_id, telegram_user, is_demo = await _resolve_driver_id(
        init_data=x_telegram_init_data,
        demo=demo,
    )

    provider = get_fleet_provider()
    try:
        driver = await provider.get_driver(driver_id)
    except FleetProviderError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    if not driver:
        raise HTTPException(status_code=404, detail="Водитель не найден.")

    orders = list_marketplace_orders(
        driver_id=driver_id,
        source=source,
        status=status,
        tariff=tariff,
    )
    summary = get_marketplace_summary(driver_id)

    return {
        "mode": "demo" if is_demo else "telegram",
        "mock": settings.YANDEX_MOCK_MODE,
        "driver": driver,
        "telegram_user": telegram_user,
        "summary": summary,
        "orders": orders,
        "price_disclaimer": (
            "Сумма со знаком ≈ рассчитана демонстрационной моделью. "
            "После подключения агрегаторов будет использоваться их цена, "
            "когда она доступна."
        ),
    }


@router.get("/orders/{order_id}")
async def miniapp_order(
    order_id: str,
    demo: bool = Query(default=False),
    x_telegram_init_data: str | None = Header(
        default=None,
        alias="X-Telegram-Init-Data",
    ),
) -> dict[str, Any]:
    driver_id, _, _ = await _resolve_driver_id(
        init_data=x_telegram_init_data,
        demo=demo,
    )
    order = get_marketplace_order(order_id, driver_id=driver_id)
    if not order:
        raise HTTPException(status_code=404, detail="Заказ не найден.")
    return order


@router.post("/orders/{order_id}/accept")
async def miniapp_accept_order(
    order_id: str,
    demo: bool = Query(default=False),
    x_telegram_init_data: str | None = Header(
        default=None,
        alias="X-Telegram-Init-Data",
    ),
) -> dict[str, Any]:
    settings = get_settings()
    driver_id, _, _ = await _resolve_driver_id(
        init_data=x_telegram_init_data,
        demo=demo,
    )

    if not settings.YANDEX_MOCK_MODE:
        raise HTTPException(
            status_code=501,
            detail=(
                "Принятие заказа доступно только в demo-режиме, "
                "пока не подключён официальный API агрегатора."
            ),
        )

    try:
        order = accept_marketplace_order(
            order_id,
            driver_id=driver_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    return {
        "ok": True,
        "order": order,
        "summary": get_marketplace_summary(driver_id),
    }
