import pytest

from app.bot.service import LocalBackendService


@pytest.mark.asyncio
async def test_local_backend_service_reads_driver_and_summary():
    service = LocalBackendService()

    driver = await service.get_driver("driver-001")
    summary = await service.get_driver_summary("driver-001")

    assert driver is not None
    assert driver["id"] == "driver-001"
    assert summary is not None
    assert summary["driver_id"] == "driver-001"
    assert summary["orders_total"] >= 1


@pytest.mark.asyncio
async def test_local_backend_service_paginates_orders():
    service = LocalBackendService()

    first, total = await service.list_orders(
        "driver-001",
        limit=2,
        offset=0,
    )
    second, same_total = await service.list_orders(
        "driver-001",
        limit=2,
        offset=2,
    )

    assert total == same_total
    assert total >= 4
    assert len(first) == 2
    assert len(second) == 2
    assert {item["id"] for item in first}.isdisjoint(
        {item["id"] for item in second}
    )
