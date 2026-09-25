from pathlib import Path

import pytest

from app.bot.storage import DriverLinkStore


@pytest.mark.asyncio
async def test_driver_link_persists_between_store_instances(tmp_path: Path):
    db_path = tmp_path / "telegram.sqlite3"

    store = DriverLinkStore(str(db_path))
    await store.init()
    await store.link(
        telegram_user_id=1001,
        driver_id="driver-001",
        phone="+996555000001",
        username="driver_one",
        first_name="Test",
        last_name="Driver",
    )

    reopened = DriverLinkStore(str(db_path))
    await reopened.init()
    link = await reopened.get(1001)

    assert link is not None
    assert link.driver_id == "driver-001"
    assert link.phone == "+996555000001"


@pytest.mark.asyncio
async def test_driver_link_can_be_unlinked(tmp_path: Path):
    db_path = tmp_path / "telegram.sqlite3"
    store = DriverLinkStore(str(db_path))
    await store.init()

    await store.link(
        telegram_user_id=1001,
        driver_id="driver-001",
        phone="+996555000001",
        username=None,
        first_name="Test",
        last_name=None,
    )

    assert await store.unlink(1001) is True
    assert await store.get(1001) is None


@pytest.mark.asyncio
async def test_driver_link_transfers_to_new_telegram_user(tmp_path: Path):
    db_path = tmp_path / "telegram.sqlite3"
    store = DriverLinkStore(str(db_path))
    await store.init()

    await store.link(
        telegram_user_id=1001,
        driver_id="driver-001",
        phone="+996555000001",
        username=None,
        first_name="Old",
        last_name=None,
    )
    await store.link(
        telegram_user_id=2002,
        driver_id="driver-001",
        phone="+996555000001",
        username=None,
        first_name="New",
        last_name=None,
    )

    assert await store.get(1001) is None
    link = await store.get(2002)
    assert link is not None
    assert link.driver_id == "driver-001"
