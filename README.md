# Yandex Fleet Backend

Backend for Yandex Fleet integration plus a Telegram park bot.

## Stage 1

Stage 1 can already be tested **without Yandex Fleet credentials and without Docker**.

The mock mode provides:

- test driver profiles;
- test orders;
- driver lookup by phone;
- Telegram park bot;
- profile and order screens in Telegram;
- mock order completion;
- a clean switch to the real Yandex integration later.

The public Yandex Fleet API does not expose a documented generic method for
completing a driver's real Yandex Pro order. Therefore completion is enabled
only for mock orders at this stage.

## Requirements

- Python 3.12+
- Telegram bot token from `@BotFather`

PostgreSQL and Redis are **not required for the Stage 1 mock test**.
They remain part of the later production architecture.

## Run without Docker

Clone and enter the repository:

```bash
git clone https://github.com/ibrodevs/Yandex-Fleet-Backend.git
cd Yandex-Fleet-Backend
```

Create a virtual environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

On Windows:

```powershell
py -3.12 -m venv .venv
.venv\Scripts\activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

Create `.env`:

```bash
cp .env.example .env
```

Set at least:

```env
YANDEX_MOCK_MODE=true
TELEGRAM_BOT_TOKEN=YOUR_BOTFATHER_TOKEN
TELEGRAM_BOT_BACKEND_URL=http://127.0.0.1:8000
```

### Terminal 1 — backend

```bash
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Check:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/drivers
curl "http://127.0.0.1:8000/api/v1/orders?driver_id=driver-001"
```

### Terminal 2 — Telegram bot

Activate the same virtual environment and run:

```bash
python -m app.bot
```

Then open the bot in Telegram:

```text
/start
/mocklogin
```

`/mocklogin` is available only while `YANDEX_MOCK_MODE=true`.

Test driver:

```text
id: driver-001
phone: +996555000001
```

The bot menu contains:

```text
👤 Профиль
📦 Заказы
🔄 Обновить
🚪 Выйти
```

The active mock order also has a `Завершить заказ` button.

## Tests

```bash
pytest -q
```

## Switching to real Yandex Fleet later

When the taxi park sends credentials:

```env
YANDEX_CLIENT_ID=...
YANDEX_API_KEY=...
YANDEX_PARK_ID=...
```

we can connect the existing service layer to real Fleet data and then set:

```env
YANDEX_MOCK_MODE=false
```

The Telegram bot does not need to be redesigned: it already talks to the
backend API instead of directly to Yandex.

## Existing architecture

- FastAPI
- SQLAlchemy / Alembic
- PostgreSQL
- Redis
- Yandex Fleet service layer
- order filtering
- Telegram bot

## Public Fleet API limitations

The public API does not expose supported generic methods for:

- accepting an incoming Yandex Pro offer;
- rejecting an incoming offer;
- skipping an order without activity/priority impact;
- completing a driver's real Yandex Pro order.

Those actions must not return fake success in real mode.
