from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Header, HTTPException, Query

from app.bot.storage import DriverLinkStore
from app.config import get_settings
from app.marketplace import (
    accept_marketplace_order,
    complete_marketplace_order,
    get_marketplace_order,
    get_marketplace_summary,
)
from app.marketplace.service import list_marketplace_orders
from app.miniapp.auth import MiniAppAuthError, validate_telegram_init_data
from app.services.fleet import FleetProviderError, get_fleet_provider

router = APIRouter(prefix="/api/v1/miniapp", tags=["miniapp"])


def _real_summary(
    driver_id: str,
    orders: list[dict[str, Any]],
    *,
    currency: str | None = None,
) -> dict[str, Any]:
    incoming = [order for order in orders if order.get("status") in {"assigned", "waiting"}]
    prices = [float(order["price"]) for order in incoming if order.get("price") is not None]
    return {
        "driver_id": driver_id,
        "incoming_count": len(incoming),
        "active_count": len([order for order in orders if order.get("status") == "in_progress"]),
        "accepted_count": len(
            [order for order in orders if order.get("status") in {"assigned", "waiting", "in_progress"}]
        ),
        "completed_count": len([order for order in orders if order.get("status") == "completed"]),
        "estimated_price_count": 0,
        "exact_price_count": len(prices),
        "average_incoming_price": round(sum(prices) / len(prices), 0) if prices else 0,
        "currency": currency
        or next((order.get("currency") for order in orders if order.get("currency")), None),
        "by_source": {"yandex": len(incoming)},
        "sources": [{"id": "yandex", "title": "Яндекс"}],
    }


def _miniapp_real_order(order: dict[str, Any]) -> dict[str, Any]:
    item = dict(order)
    status = item.get("status")
    if status in {"assigned", "waiting"}:
        item["status"] = "incoming"
        item["status_title"] = "Новый заказ"
    elif status == "in_progress":
        item["status"] = "active"
        item["status_title"] = "Активный"
    item["can_accept"] = False
    item["can_complete"] = False
    return item


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

    if settings.YANDEX_MOCK_MODE:
        orders = list_marketplace_orders(
            driver_id=driver_id,
            source=source,
            status=status,
            tariff=tariff,
        )
        summary = get_marketplace_summary(driver_id)
        price_disclaimer = (
            "Сумма со знаком ≈ рассчитана демонстрационной моделью. "
            "После подключения агрегаторов будет использоваться их цена, "
            "когда она доступна."
        )
    else:
        try:
            orders = await provider.list_orders(driver_id=driver_id)
        except FleetProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        summary = _real_summary(driver_id, orders, currency=driver.get("currency"))
        orders = [_miniapp_real_order(order) for order in orders]
        if source and source not in {"all", "yandex"}:
            orders = []
        if status:
            orders = [order for order in orders if order.get("status") == status]
        if tariff:
            orders = [order for order in orders if order.get("category") == tariff]
        price_disclaimer = (
            "Показаны данные, доступные через официальный Yandex Fleet API. "
            "Отсутствующие значения не рассчитываются автоматически."
        )

    return {
        "mode": "demo" if is_demo else "telegram",
        "mock": settings.YANDEX_MOCK_MODE,
        "driver": driver,
        "telegram_user": telegram_user,
        "summary": summary,
        "orders": orders,
        "price_disclaimer": price_disclaimer,
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
    if get_settings().YANDEX_MOCK_MODE:
        order = get_marketplace_order(order_id, driver_id=driver_id)
    else:
        try:
            order = await get_fleet_provider().get_order(order_id)
        except FleetProviderError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc
        if order and str(order.get("driver_id")) != str(driver_id):
            order = None
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


@router.post("/orders/{order_id}/complete")
async def miniapp_complete_order(
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
                "Завершение заказа доступно только в demo-режиме, "
                "пока не подключён официальный API агрегатора."
            ),
        )

    try:
        order = complete_marketplace_order(
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
