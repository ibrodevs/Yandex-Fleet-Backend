import logging
import secrets
import time
from typing import Literal
from uuid import uuid4

import jwt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import BaseModel, Field

from app.config import get_settings
from app.mobile.firebase import send_push, verify_phone_token
from app.mobile.storage import database, settings_for
from app.services.fleet import FleetProviderError, get_fleet_provider
from app.services.fleet.phone import normalize_phone

log = logging.getLogger(__name__)
bearer = HTTPBearer(auto_error=False)


def enabled():
    cfg = get_settings()
    if not cfg.MOBILE_ENABLED:
        raise HTTPException(404)
    if cfg.YANDEX_MOCK_MODE:
        raise HTTPException(503, "Mobile requires real Yandex mode")
    if len(cfg.SECRET_KEY) < 32 or cfg.SECRET_KEY.startswith("default-insecure"):
        raise HTTPException(503, "Configure a secure SECRET_KEY")


router = APIRouter(prefix="/api/v1/mobile", tags=["mobile"], dependencies=[Depends(enabled)])


async def session(credentials: HTTPAuthorizationCredentials | None = Depends(bearer)):
    try:
        if not credentials:
            raise ValueError()
        claims = jwt.decode(
            credentials.credentials,
            get_settings().SECRET_KEY,
            algorithms=["HS256"],
            audience="fleet-mobile",
            issuer="fleet-backend",
            options={"require": ["exp", "iat", "session_id", "driver_id", "phone"]},
        )
        async with database() as db:
            row = await (
                await db.execute(
                    "SELECT * FROM mobile_sessions WHERE id=? AND revoked=0 AND expires_at>?",
                    (claims["session_id"], int(time.time())),
                )
            ).fetchone()
        if not row or row["driver_id"] != claims["driver_id"]:
            raise ValueError()
        return dict(row)
    except (jwt.PyJWTError, ValueError):
        raise HTTPException(401, "Session expired") from None


async def fleet_call(method, *args, **kwargs):
    try:
        return await getattr(get_fleet_provider(), method)(*args, **kwargs)
    except FleetProviderError:
        raise HTTPException(503, "Данные Яндекс временно недоступны") from None


class Login(BaseModel):
    id_token: str = Field(min_length=10, max_length=16384)


class TestLogin(BaseModel):
    phone: str = Field(min_length=7, max_length=32)
    code: str = Field(min_length=6, max_length=6)


async def create_mobile_session(driver: dict, phone: str):
    cfg = get_settings()
    sid = str(uuid4())
    now = int(time.time())
    expires = now + cfg.MOBILE_JWT_EXPIRE_DAYS * 86400

    async with database() as db:
        await db.execute(
            """
            INSERT INTO mobile_sessions(id,driver_id,phone,expires_at)
            VALUES(?,?,?,?)
            """,
            (sid, str(driver["id"]), phone, expires),
        )

    token = jwt.encode(
        {
            "driver_id": str(driver["id"]),
            "phone": phone,
            "session_id": sid,
            "iat": now,
            "exp": expires,
            "aud": "fleet-mobile",
            "iss": "fleet-backend",
        },
        cfg.SECRET_KEY,
        algorithm="HS256",
    )

    return {"access_token": token, "token_type": "bearer", "expires_at": expires}


@router.post("/auth/firebase")
async def login(body: Login):
    total_started = time.monotonic()
    cfg = get_settings()
    if not cfg.FIREBASE_PROJECT_ID or not cfg.FIREBASE_CREDENTIALS_FILE:
        raise HTTPException(503, "Firebase is not configured")
    try:
        firebase_started = time.monotonic()
        log.info("mobile_login_firebase_verification_started")
        try:
            claims = await verify_phone_token(body.id_token)
        finally:
            log.info(
                "mobile_login_firebase_verification_finished duration_ms=%s",
                round((time.monotonic() - firebase_started) * 1000),
            )
        phone = normalize_phone(
            claims.get("phone_number"), default_country_code=cfg.PHONE_DEFAULT_COUNTRY_CODE
        )
        if not phone or claims.get("firebase", {}).get("sign_in_provider") != "phone":
            raise ValueError()
    except Exception:
        log.info("mobile_login_failed")
        raise HTTPException(401, "Не удалось подтвердить номер") from None
    log.info("mobile_login_driver_lookup_started")
    driver_started = time.monotonic()
    try:
        driver = await fleet_call("get_driver_by_phone", phone)
    finally:
        log.info(
            "mobile_login_driver_lookup_finished duration_ms=%s",
            round((time.monotonic() - driver_started) * 1000),
        )
    if not driver or not driver.get("id"):
        log.info("mobile_login_failed")
        raise HTTPException(403, "Водитель с этим номером не найден в парке")
    session_response = await create_mobile_session(driver, phone)
    log.info(
        "mobile_login_success total_duration_ms=%s",
        round((time.monotonic() - total_started) * 1000),
    )
    return session_response


@router.post("/auth/test")
async def test_login(body: TestLogin):
    cfg = get_settings()
    if not cfg.MOBILE_TEST_AUTH_ENABLED:
        raise HTTPException(404)

    phone = normalize_phone(
        body.phone,
        default_country_code=cfg.PHONE_DEFAULT_COUNTRY_CODE,
    )
    allowed = {
        normalized
        for item in cfg.MOBILE_TEST_AUTH_PHONES.split(",")
        if item.strip()
        if (
            normalized := normalize_phone(
                item.strip(),
                default_country_code=cfg.PHONE_DEFAULT_COUNTRY_CODE,
            )
        )
    }

    if (
        not phone
        or phone not in allowed
        or not secrets.compare_digest(
            body.code.encode(),
            cfg.MOBILE_TEST_AUTH_CODE.encode(),
        )
    ):
        log.info("mobile_test_login_failed")
        raise HTTPException(401, "Неверный номер или тестовый код")

    log.info("mobile_test_login_started")
    driver_started = time.monotonic()
    log.info("mobile_test_login_driver_lookup_started")
    try:
        driver = await fleet_call("get_driver_by_phone", phone)
    finally:
        log.info(
            "mobile_test_login_driver_lookup_finished duration_ms=%s",
            round((time.monotonic() - driver_started) * 1000),
        )
    if not driver or not driver.get("id"):
        log.info("mobile_test_login_driver_not_found")
        raise HTTPException(403, "Водитель с этим номером не найден в парке")

    log.info("mobile_test_login_success")
    return await create_mobile_session(driver, phone)


@router.post("/auth/logout")
async def logout(user=Depends(session)):
    async with database() as db:
        await db.execute("UPDATE mobile_sessions SET revoked=1 WHERE id=?", (user["id"],))
        await db.execute("UPDATE mobile_devices SET enabled=0 WHERE session_id=?", (user["id"],))
    return {"ok": True}


@router.get("/me")
async def me(user=Depends(session)):
    driver = await fleet_call("get_driver", user["driver_id"])
    if not driver:
        raise HTTPException(404, "Водитель не найден")
    return driver


@router.get("/summary")
async def summary(user=Depends(session)):
    return await fleet_call("get_driver_summary", user["driver_id"])


@router.get("/vehicle")
async def vehicle(user=Depends(session)):
    driver = await me(user)
    return driver.get("vehicle")


def readonly(order):
    return {**order, "can_accept": False, "can_complete": False}


@router.get("/orders")
async def orders(user=Depends(session)):
    items = await fleet_call("list_orders", driver_id=user["driver_id"])
    return [readonly(o) for o in items if str(o.get("driver_id")) == user["driver_id"]]


@router.get("/orders/{order_id}")
async def order(order_id: str, user=Depends(session)):
    item = await fleet_call("get_order", order_id)
    if not item or str(item.get("driver_id")) != user["driver_id"]:
        raise HTTPException(404, "Заказ не найден")
    return readonly(item)


class Device(BaseModel):
    fcm_token: str = Field(min_length=10, max_length=4096)
    platform: Literal["android", "ios"]
    device_id: str = Field(min_length=8, max_length=128)


@router.post("/devices")
async def register_device(body: Device, user=Depends(session)):
    async with database() as db:
        await db.execute(
            "DELETE FROM mobile_devices WHERE fcm_token=? AND device_id<>?",
            (body.fcm_token, body.device_id),
        )
        await db.execute(
            """INSERT INTO mobile_devices(id,driver_id,session_id,fcm_token,platform,device_id)
            VALUES(?,?,?,?,?,?) ON CONFLICT(device_id) DO UPDATE SET driver_id=excluded.driver_id,
            session_id=excluded.session_id,fcm_token=excluded.fcm_token, platform=excluded.platform,
            enabled=1, updated_at=CURRENT_TIMESTAMP,last_seen_at=CURRENT_TIMESTAMP""",
            (
                str(uuid4()),
                user["driver_id"],
                user["id"],
                body.fcm_token,
                body.platform,
                body.device_id,
            ),
        )
    log.info("mobile_device_registered")
    return {"device_id": body.device_id}


@router.delete("/devices/{device_id}")
async def delete_device(device_id: str, user=Depends(session)):
    async with database() as db:
        await db.execute(
            "DELETE FROM mobile_devices WHERE device_id=? AND driver_id=?",
            (device_id, user["driver_id"]),
        )
    return {"ok": True}


class OverlaySettings(BaseModel):
    overlay_enabled: bool = True
    notifications: bool = True
    sound: bool = True
    vibration: bool = True
    auto_hide: bool = True
    display_seconds: Literal[5, 10, 15, 30] = 15
    transparency: int = Field(default=0, ge=0, le=80)
    show_price: bool = True
    show_address: bool = True
    show_tariff: bool = True
    show_distance: bool = True


@router.get("/settings")
async def get_preferences(user=Depends(session)):
    return OverlaySettings(**await settings_for(user["driver_id"]))


@router.put("/settings")
async def put_preferences(body: OverlaySettings, user=Depends(session)):
    async with database() as db:
        await db.execute(
            "INSERT INTO mobile_settings VALUES(?,?) ON CONFLICT(driver_id) DO UPDATE SET value=excluded.value",
            (user["driver_id"], body.model_dump_json()),
        )
    return body


class TestPush(BaseModel):
    device_id: str


@router.post("/debug/test-notification")
async def test_notification(body: TestPush, user=Depends(session)):
    if get_settings().is_production:
        raise HTTPException(404)
    async with database() as db:
        device = await (
            await db.execute(
                "SELECT * FROM mobile_devices WHERE device_id=? AND driver_id=? AND enabled=1",
                (body.device_id, user["driver_id"]),
            )
        ).fetchone()
    if not device:
        raise HTTPException(404)
    try:
        await send_push(
            device["fcm_token"],
            {
                "type": "new_order",
                "order_id": "test-" + str(uuid4()),
                "is_test": True,
                "driver_id": user["driver_id"],
                "tariff_title": "ПРОВЕРКА ЭКРАНА · пример",
            },
            device["platform"],
        )
    except Exception:
        raise HTTPException(503, "Push unavailable") from None
    return {"ok": True}


@router.get("/status")
async def mobile_status(user=Depends(session)):
    cfg = get_settings()
    return {
        "push_available": bool(cfg.FIREBASE_PROJECT_ID and cfg.FIREBASE_CREDENTIALS_FILE),
        "screen_reader_enabled": False,
    }
