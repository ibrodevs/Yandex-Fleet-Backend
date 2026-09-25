# Current deployment account

```text
PythonAnywhere username: yandexfeetbackend21
Public domain: https://yandexfeetbackend21.pythonanywhere.com
Repository path: /home/yandexfeetbackend21/Yandex-Fleet-Backend
Virtualenv: /home/yandexfeetbackend21/.virtualenvs/yandex-fleet
Webhook: https://yandexfeetbackend21.pythonanywhere.com/api/v1/telegram/webhook
```

A ready deployment helper is included:

```bash
bash ~/Yandex-Fleet-Backend/deploy/pythonanywhere_setup.sh
```

# PythonAnywhere deployment

This project is prepared for PythonAnywhere as one FastAPI ASGI web app.

Production architecture:

```text
Telegram
   │ HTTPS webhook
   ▼
https://YOURUSERNAME.pythonanywhere.com/api/v1/telegram/webhook
   │
   ▼
FastAPI + aiogram
   │
   ▼
FleetProvider
   ├── MockFleetProvider
   └── YandexFleetProvider
```

The Telegram bot does not need an always-on polling process in production.

## 1. PythonAnywhere requirements

Use Python 3.12.

If the account is on an old system image that does not provide Python 3.12,
switch the account to the current `innit` system image first.

## 2. Clone

Open a Bash console on PythonAnywhere:

```bash
cd ~
git clone https://github.com/ibrodevs/Yandex-Fleet-Backend.git
cd Yandex-Fleet-Backend
```

For later deploys:

```bash
cd ~/Yandex-Fleet-Backend
git pull origin main
```

## 3. Virtual environment

```bash
/usr/local/bin/python3.12 -m venv ~/.virtualenvs/yandex-fleet
source ~/.virtualenvs/yandex-fleet/bin/activate
python -m pip install --upgrade pip
pip install -r ~/Yandex-Fleet-Backend/requirements.txt
```

## 4. Environment

```bash
cd ~/Yandex-Fleet-Backend
cp .env.pythonanywhere.example .env
```

Generate secrets:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
python -c "import secrets; print(secrets.token_urlsafe(32))"
```

Put the first value into `SECRET_KEY` and the second into
`TELEGRAM_WEBHOOK_SECRET`.

Edit:

```bash
nano .env
```

Required values:

```env
APP_ENV=production
YANDEX_MOCK_MODE=true

TELEGRAM_BOT_TOKEN=YOUR_REAL_BOT_TOKEN
TELEGRAM_BOT_MODE=webhook

TELEGRAM_HTTP_PROXY=http://proxy.server:3128

TELEGRAM_WEBHOOK_BASE_URL=https://YOURUSERNAME.pythonanywhere.com
TELEGRAM_WEBHOOK_PATH=/api/v1/telegram/webhook
TELEGRAM_WEBHOOK_SECRET=YOUR_RANDOM_SECRET
TELEGRAM_WEBHOOK_AUTO_SETUP=true

TELEGRAM_BOT_DB_PATH=/home/YOURUSERNAME/Yandex-Fleet-Backend/.data/telegram_bot.sqlite3
```

For a paid PythonAnywhere account with unrestricted outbound Internet,
`TELEGRAM_HTTP_PROXY` can be empty.

Do not commit `.env`.

## 5. Test before publishing

```bash
cd ~/Yandex-Fleet-Backend
source ~/.virtualenvs/yandex-fleet/bin/activate
pytest -q
```

Expected:

```text
17 passed
```

The exact count can increase as new tests are added; all tests must pass.

## 6. Create the ASGI site

Create an API token in the PythonAnywhere account page first.

Install the PythonAnywhere CLI in a normal console environment:

```bash
pip install --upgrade pythonanywhere
```

Create the web app. Replace `YOURUSERNAME` everywhere:

```bash
pa website create \
  --domain YOURUSERNAME.pythonanywhere.com \
  --command '/home/YOURUSERNAME/.virtualenvs/yandex-fleet/bin/uvicorn --app-dir /home/YOURUSERNAME/Yandex-Fleet-Backend --env-file /home/YOURUSERNAME/Yandex-Fleet-Backend/.env --uds ${DOMAIN_SOCKET} app.main:app'
```

Check it:

```bash
pa website get --domain YOURUSERNAME.pythonanywhere.com
```

## 7. Verify backend

Open:

```text
https://YOURUSERNAME.pythonanywhere.com/
https://YOURUSERNAME.pythonanywhere.com/health
https://YOURUSERNAME.pythonanywhere.com/health/ready
https://YOURUSERNAME.pythonanywhere.com/api/v1/integrations/yandex/status
https://YOURUSERNAME.pythonanywhere.com/api/v1/telegram/status
```

Expected health response:

```json
{
  "status": "ready",
  "telegram_ready": true,
  "mock_mode": true
}
```

`/api/v1/telegram/status` must show a Telegram webhook URL matching:

```text
https://YOURUSERNAME.pythonanywhere.com/api/v1/telegram/webhook
```

## 8. Telegram webhook

The application automatically calls Telegram `setWebhook` on startup when:

```env
TELEGRAM_BOT_MODE=webhook
TELEGRAM_WEBHOOK_AUTO_SETUP=true
```

The webhook endpoint requires the secret header configured by Telegram.
Requests without the matching secret receive HTTP 403.

Do not open the webhook URL manually and expect a normal page; Telegram sends
POST updates to it.

## 9. Test Telegram

In Telegram:

```text
/start
/mocklogin
```

Then test:

```text
👤 Профиль
📦 Заказы
📊 Статистика
🚕 Активный заказ
🔗 Привязка
```

The bot should keep working even when no PythonAnywhere console is open.

Do not run `python -m app.bot` on PythonAnywhere production. That command is
only for local polling development.

## 10. Logs

Get site details:

```bash
pa website get --domain YOURUSERNAME.pythonanywhere.com
```

It shows the server/access/error log paths.

Typical server log:

```text
/var/log/YOURUSERNAME.pythonanywhere.com.server.log
```

Tail it:

```bash
tail -f /var/log/YOURUSERNAME.pythonanywhere.com.server.log
```

## 11. Deploy updates

```bash
cd ~/Yandex-Fleet-Backend
git pull origin main
source ~/.virtualenvs/yandex-fleet/bin/activate
pip install -r requirements.txt
pytest -q
pa website reload --domain YOURUSERNAME.pythonanywhere.com
```

The FastAPI startup hook will refresh the Telegram webhook automatically.

## 12. Real Yandex credentials later

When the park sends:

```env
YANDEX_CLIENT_ID=...
YANDEX_API_KEY=...
YANDEX_PARK_ID=...
```

implement/enable the real provider and then switch:

```env
YANDEX_MOCK_MODE=false
```

The Telegram webhook deployment does not change.

## Troubleshooting

### Bot receives nothing

Check:

```text
/api/v1/telegram/status
```

Look at:

- `telegram.url`
- `telegram.pending_update_count`
- `telegram.last_error_message`
- `telegram_error`
- `last_setup_error`

### Network is unreachable to api.telegram.org

On a free PythonAnywhere account verify:

```env
TELEGRAM_HTTP_PROXY=http://proxy.server:3128
```

Then reload the site.

### Backend works but webhook setup failed

The backend intentionally stays online even if Telegram setup fails. Check the
server log and `/api/v1/telegram/status`, correct the environment, then reload.

### 403 on the webhook endpoint

That is expected for requests that do not contain Telegram's secret header.
The endpoint is not intended for browser access.


## Mini App

The same PythonAnywhere ASGI site serves the Telegram Mini App:

```text
https://yandexfeetbackend21.pythonanywhere.com/miniapp/
```

No separate frontend hosting is required.

In mock mode this URL can also be opened directly in a browser for a client
demo. Inside Telegram, use `/mocklogin` once and then `/app`, or press
`🚖 Приложение`.

After updating the repository, reload the site:

```bash
cd ~/Yandex-Fleet-Backend
git pull origin main
source ~/.virtualenvs/yandex-fleet/bin/activate
pytest -q
pa website reload --domain yandexfeetbackend21.pythonanywhere.com
```

On startup the bot configures the Mini App chat-menu button automatically.
