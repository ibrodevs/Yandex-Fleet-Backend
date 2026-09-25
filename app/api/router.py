from fastapi import APIRouter

from app.api.v1.drivers import router as drivers_router
from app.api.v1.health import router as health_router
from app.api.v1.integrations import router as integrations_router
from app.api.v1.orders import router as orders_router
from app.api.v1.telegram import router as telegram_router

api_router = APIRouter()
api_router.include_router(health_router)
api_router.include_router(drivers_router)
api_router.include_router(orders_router)
api_router.include_router(integrations_router)

api_router.include_router(telegram_router)
