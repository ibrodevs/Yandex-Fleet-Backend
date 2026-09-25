# Yandex Fleet Backend

Backend for Yandex Fleet integration plus a Telegram park bot.

## Stage 1 status

Stage 1 is designed to be fully testable **without Yandex Fleet credentials and without Docker**.

Implemented:

- stable backend contract for drivers and orders;
- provider abstraction `FleetProvider` for switching mock → real Yandex later;
- rich mock driver profile;
- rich mock order data;
- driver lookup by phone;
- driver summary/statistics;
- order list with pagination;
- order details;
- active-order screen;
- mock order completion;
- Telegram bot;
- persistent Telegram ↔ driver binding in SQLite;
- binding recovery after bot restart;
- secure own-contact check during binding;
- one-driver-to-one-Telegram binding transfer;
- ownership check before opening/completing an order;
- unlink/relink flow;
- Telegram command menu;
- graceful handling of unchanged Telegram messages;
- automated API/storage tests;
- GitHub Actions test workflow.

The public Yandex Fleet API does not expose a documented generic method for
completing a driver's real Yandex Pro order. Therefore completion is enabled
only for mock orders at this stage.

## Stage 1 architecture

```text
Telegram
   │
   ▼
app.bot
   │
   ├── SQLite link store (.data/telegram_bot.sqlite3)
   │
   ▼
FastAPI backend
   │
   ▼
FleetProvider
   ├── MockFleetProvider   ← Stage 1
   └── YandexFleetProvider ← Stage 2 / real park credentials
```

Telegram never talks to Yandex directly. When real park credentials arrive,
the bot UI and handlers do not need to be rewritten; only the real provider
adapter needs to map Fleet API data into the existing backend contract.

## Requirements

- Python 3.12+
- Telegram bot token from `@BotFather`

PostgreSQL and Redis are **not required for the Stage 1 mock test**.

## Run without Docker

Clone or update the repository:

```bash
git clone https://github.com/ibrodevs/Yandex-Fleet-Backend.git
cd Yandex-Fleet-Backend
```

If you already cloned it:

```bash
git pull origin main
```

Create and activate the environment:

```bash
python3.12 -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
python -m pip install --upgrade pip
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
TELEGRAM_BOT_DB_PATH=.data/telegram_bot.sqlite3
TELEGRAM_BOT_ORDERS_PAGE_SIZE=5
```

## Terminal 1 — backend

```bash
source .venv/bin/activate
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

Quick checks:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/api/v1/drivers/driver-001
curl http://127.0.0.1:8000/api/v1/drivers/driver-001/summary
curl "http://127.0.0.1:8000/api/v1/orders?driver_id=driver-001&limit=5"
curl http://127.0.0.1:8000/api/v1/integrations/yandex/status
```

## Terminal 2 — Telegram bot

```bash
source .venv/bin/activate
python -m app.bot
```

Open the bot in Telegram.

For the fastest mock test:

```text
/start
/mocklogin
```

For the normal binding flow use the button:

```text
📱 Поделиться номером
```

The bot checks that the shared Telegram contact belongs to the current
Telegram user and asks the backend to resolve that phone to a driver.

Mock driver:

```text
driver_id: driver-001
phone: +996555000001
```

## Bot menu

```text
👤 Профиль
📦 Заказы

📊 Статистика
🚕 Активный заказ

🔄 Обновить
🔗 Привязка
```

### Profile

Shows:

- driver name;
- phone;
- work status;
- rating;
- priority;
- balance;
- tariffs;
- vehicle;
- completed/active/cancelled order counters;
- earnings;
- distance.

### Orders

Shows a paginated list. Selecting an order opens:

- status;
- tariff;
- payment type;
- price;
- pickup;
- destination;
- distance;
- duration;
- creation/start/completion timestamps.

An active mock order also has:

```text
✅ Завершить заказ
```

### Persistent Telegram binding

Bindings are stored in:

```text
.data/telegram_bot.sqlite3
```

The database is created automatically.

Test persistence:

1. run `/mocklogin`;
2. stop the bot with `Ctrl+C`;
3. start `python -m app.bot` again;
4. send `/start`;
5. the bot should restore the linked driver automatically.

Use `🔗 Привязка` or `/unlink` to remove the binding.

## Automated tests

Run locally:

```bash
pytest -q
```

Tests cover:

- base API;
- mock profile;
- phone lookup;
- driver summary;
- order list;
- pagination;
- detailed order payload;
- integration status;
- persistent Telegram binding;
- unlink;
- transfer of one driver binding to a new Telegram user.

GitHub Actions also runs `pytest -q` on pushes to `main`.

## Switching to the real park later

When the client sends:

```env
YANDEX_CLIENT_ID=...
YANDEX_API_KEY=...
YANDEX_PARK_ID=...
```

the next integration step is to implement the mapping inside:

```text
app/services/fleet/yandex.py
```

After that:

```env
YANDEX_MOCK_MODE=false
```

The public REST routes and Telegram bot remain the same.

## Stage 1 definition of done

Stage 1 is considered complete when all of these pass:

- backend starts without Docker;
- bot starts without Docker;
- `pytest -q` passes;
- `/mocklogin` links driver-001;
- profile displays full mock driver data;
- statistics display correctly;
- order list paginates;
- order details open;
- active mock order completes;
- restart preserves Telegram binding;
- unlink removes the binding;
- foreign order IDs are rejected by the bot;
- real mode never fakes successful completion of a Yandex Pro order.

## Public Fleet API limitations

The public API does not expose supported generic methods for:

- accepting an incoming Yandex Pro offer;
- rejecting an incoming offer;
- skipping an order without activity/priority impact;
- completing a driver's real Yandex Pro order.

Those actions must not return fake success in real mode.


## PythonAnywhere deployment

The backend is prepared to run on PythonAnywhere as a FastAPI ASGI site with
the Telegram bot connected by webhook, so production does not require a
separate long-polling process.

Use:

```text
docs/PYTHONANYWHERE.md
```

Production settings are based on:

```text
.env.pythonanywhere.example
```

The production flow is:

```text
Telegram -> HTTPS webhook -> FastAPI -> FleetProvider
```

Local development can continue to use:

```bash
python -m app.bot
```

with:

```env
TELEGRAM_BOT_MODE=polling
```

PythonAnywhere production should use:

```env
TELEGRAM_BOT_MODE=webhook
```


## Telegram Mini App

Stage 1 now also includes a park Mini App served by the same FastAPI application:

```text
https://<backend-domain>/miniapp/
```

In the current mock demo it provides a unified incoming-order feed for:

- Fasten
- Яндекс
- Везёт

Each card shows the aggregator, tariff, pickup and destination, distance,
estimated duration, payment type and price. Prices supplied by a mock
aggregator are shown as exact demo prices. When no source price is available,
the UI shows `≈` and a transparent demo calculation based on base fare,
distance, duration and a demand multiplier.

Filters are available by aggregator, status and tariff. The Mini App also has
statistics and driver profile screens.

Telegram integration:

- `/app` opens the Mini App;
- the reply keyboard has `🚖 Приложение`;
- webhook mode configures Telegram's chat menu button;
- Telegram `initData` is validated server-side before resolving the
  Telegram-to-driver binding;
- direct browser demo is allowed only while both
  `YANDEX_MOCK_MODE=true` and `TELEGRAM_MINI_APP_DEMO_MODE=true`.

For the current PythonAnywhere deployment the demo URL is:

```text
https://yandexfeetbackend21.pythonanywhere.com/miniapp/
```

### Updating the PythonAnywhere demo

```bash
cd ~/Yandex-Fleet-Backend
git pull origin main
source ~/.virtualenvs/yandex-fleet/bin/activate
pip install -r requirements.txt
pytest -q
pa website reload --domain yandexfeetbackend21.pythonanywhere.com
```

After reload, send `/start`, then `/mocklogin`, then `/app` in Telegram.
