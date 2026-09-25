import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import GUID, Base, JSONType, TimestampMixin


class Order(Base, TimestampMixin):
    __tablename__ = "orders"

    id: Mapped[uuid.UUID] = mapped_column(
        GUID(),
        primary_key=True,
        default=uuid.uuid4,
    )
    yandex_order_id: Mapped[str] = mapped_column(
        String(128),
        unique=True,
        nullable=False,
        index=True,
    )
    driver_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("drivers.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    vehicle_id: Mapped[uuid.UUID | None] = mapped_column(
        GUID(),
        ForeignKey("vehicles.id", ondelete="SET NULL"),
        nullable=True,
    )

    status: Mapped[str] = mapped_column(
        String(64),
        nullable=False,
        default="pending",
        index=True,
    )

    price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    currency: Mapped[str | None] = mapped_column(String(16), nullable=True, default="RUB")

    category: Mapped[str | None] = mapped_column(String(64), nullable=True)
    payment_method: Mapped[str | None] = mapped_column(String(64), nullable=True)

    pickup_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    pickup_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    pickup_lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)

    destination_address: Mapped[str | None] = mapped_column(Text, nullable=True)
    destination_lat: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)
    destination_lon: Mapped[Decimal | None] = mapped_column(Numeric(10, 7), nullable=True)

    yandex_created_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        index=True,
    )

    raw_payload: Mapped[dict[str, Any] | None] = mapped_column(
        JSONType,
        nullable=True,
    )

    last_synced_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )

    __table_args__ = (
        Index("ix_orders_yandex_order_id", "yandex_order_id"),
        Index("ix_orders_driver_id", "driver_id"),
        Index("ix_orders_status", "status"),
        Index("ix_orders_yandex_created_at", "yandex_created_at"),
    )
