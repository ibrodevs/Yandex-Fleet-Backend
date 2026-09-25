"""Initial schema

Revision ID: 20260925_000001
Revises:
Create Date: 2026-09-25 00:00:00.000000

"""

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision = "20260925_000001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "drivers",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("yandex_driver_id", sa.String(length=128), nullable=False),
        sa.Column("first_name", sa.String(length=128), nullable=True),
        sa.Column("last_name", sa.String(length=128), nullable=True),
        sa.Column("phone", sa.String(length=64), nullable=True),
        sa.Column("is_enabled", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("local_driver_state", sa.String(length=32), nullable=False, server_default="UNKNOWN"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("yandex_driver_id"),
    )
    op.create_index(op.f("ix_drivers_yandex_driver_id"), "drivers", ["yandex_driver_id"], unique=False)

    op.create_table(
        "vehicles",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("yandex_vehicle_id", sa.String(length=128), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=True),
        sa.Column("brand", sa.String(length=128), nullable=True),
        sa.Column("model", sa.String(length=128), nullable=True),
        sa.Column("license_plate", sa.String(length=64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("yandex_vehicle_id"),
    )
    op.create_index(op.f("ix_vehicles_driver_id"), "vehicles", ["driver_id"], unique=False)
    op.create_index(op.f("ix_vehicles_yandex_vehicle_id"), "vehicles", ["yandex_vehicle_id"], unique=False)

    op.create_table(
        "orders",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("yandex_order_id", sa.String(length=128), nullable=False),
        sa.Column("driver_id", sa.Uuid(), nullable=True),
        sa.Column("vehicle_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.String(length=64), nullable=False, server_default="pending"),
        sa.Column("price", sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column("currency", sa.String(length=16), nullable=True, server_default="RUB"),
        sa.Column("category", sa.String(length=64), nullable=True),
        sa.Column("payment_method", sa.String(length=64), nullable=True),
        sa.Column("pickup_address", sa.Text(), nullable=True),
        sa.Column("pickup_lat", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("pickup_lon", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("destination_address", sa.Text(), nullable=True),
        sa.Column("destination_lat", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("destination_lon", sa.Numeric(precision=10, scale=7), nullable=True),
        sa.Column("yandex_created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("raw_payload", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["driver_id"], ["drivers.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["vehicle_id"], ["vehicles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("yandex_order_id"),
    )
    op.create_index(op.f("ix_orders_driver_id"), "orders", ["driver_id"], unique=False)
    op.create_index(op.f("ix_orders_status"), "orders", ["status"], unique=False)
    op.create_index(op.f("ix_orders_yandex_created_at"), "orders", ["yandex_created_at"], unique=False)
    op.create_index(op.f("ix_orders_yandex_order_id"), "orders", ["yandex_order_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_orders_yandex_order_id"), table_name="orders")
    op.drop_index(op.f("ix_orders_yandex_created_at"), table_name="orders")
    op.drop_index(op.f("ix_orders_status"), table_name="orders")
    op.drop_index(op.f("ix_orders_driver_id"), table_name="orders")
    op.drop_table("orders")

    op.drop_index(op.f("ix_vehicles_yandex_vehicle_id"), table_name="vehicles")
    op.drop_index(op.f("ix_vehicles_driver_id"), table_name="vehicles")
    op.drop_table("vehicles")

    op.drop_index(op.f("ix_drivers_yandex_driver_id"), table_name="drivers")
    op.drop_table("drivers")
