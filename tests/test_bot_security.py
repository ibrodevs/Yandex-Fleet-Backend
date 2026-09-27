from app.bot.main import contact_belongs_to_user, order_belongs_to_driver


def test_foreign_telegram_contact_is_rejected():
    assert contact_belongs_to_user(1001, 1001) is True
    assert contact_belongs_to_user(2002, 1001) is False
    assert contact_belongs_to_user(None, 1001) is False


def test_foreign_order_is_rejected():
    assert order_belongs_to_driver({"driver_id": "driver-a"}, "driver-a") is True
    assert order_belongs_to_driver({"driver_id": "driver-b"}, "driver-a") is False
    assert order_belongs_to_driver({}, "driver-a") is False
