#!/usr/bin/env bash
set -euo pipefail

USERNAME="yandexfeetbackend21"
DOMAIN="${USERNAME}.pythonanywhere.com"
REPO_DIR="/home/${USERNAME}/Yandex-Fleet-Backend"
VENV_DIR="/home/${USERNAME}/.virtualenvs/yandex-fleet"
ENV_TEMPLATE="${REPO_DIR}/.env.pythonanywhere.yandexfeetbackend21.example"
ENV_FILE="${REPO_DIR}/.env"
PYTHON_BIN="/usr/local/bin/python3.12"

echo "==> Deploy target: https://${DOMAIN}"

if [ ! -x "${PYTHON_BIN}" ]; then
  echo "ERROR: Python 3.12 is not available at ${PYTHON_BIN}."
  echo "On PythonAnywhere open Account -> System image and switch to 'innit',"
  echo "then start a fresh Bash console and run this script again."
  exit 4
fi

if [ ! -d "${REPO_DIR}/.git" ]; then
  cd "/home/${USERNAME}"
  git clone https://github.com/ibrodevs/Yandex-Fleet-Backend.git
else
  cd "${REPO_DIR}"
  git pull origin main
fi

if [ ! -x "${VENV_DIR}/bin/python" ]; then
  "${PYTHON_BIN}" -m venv "${VENV_DIR}"
fi

source "${VENV_DIR}/bin/activate"
python -m pip install --upgrade pip
pip install -r "${REPO_DIR}/requirements.txt"
pip install --upgrade pythonanywhere

cd "${REPO_DIR}"

if [ ! -f "${ENV_FILE}" ]; then
  cp "${ENV_TEMPLATE}" "${ENV_FILE}"
  echo
  echo "Created ${ENV_FILE}."
  echo "Edit it now and set:"
  echo "  TELEGRAM_BOT_TOKEN"
  echo "  SECRET_KEY"
  echo "  TELEGRAM_WEBHOOK_SECRET"
  echo
  echo "Then run this script again."
  exit 2
fi

if grep -q "PUT_BOTFATHER_TOKEN_HERE\|CHANGE_ME_TO_A_LONG_RANDOM_SECRET\|CHANGE_ME_TO_RANDOM_WEBHOOK_SECRET" "${ENV_FILE}"; then
  echo "ERROR: ${ENV_FILE} still contains placeholder secrets."
  echo "Edit the file before deployment:"
  echo "  nano ${ENV_FILE}"
  exit 3
fi

echo "==> Checking production Telegram configuration"
python - <<'PY'
from app.config import get_settings

s = get_settings()
errors = []

if s.TELEGRAM_BOT_MODE.lower() != "webhook":
    errors.append("TELEGRAM_BOT_MODE must be webhook on PythonAnywhere")
if not s.TELEGRAM_BOT_TOKEN:
    errors.append("TELEGRAM_BOT_TOKEN is empty")
if not s.TELEGRAM_WEBHOOK_SECRET:
    errors.append("TELEGRAM_WEBHOOK_SECRET is empty")
if not s.TELEGRAM_WEBHOOK_BASE_URL.startswith("https://"):
    errors.append("TELEGRAM_WEBHOOK_BASE_URL must use https://")
if not s.telegram_mini_app_url.startswith("https://"):
    errors.append("Telegram Mini App URL must use https://")

if errors:
    for item in errors:
        print(f"ERROR: {item}")
    raise SystemExit(5)

print("Telegram mode: webhook")
print(f"Webhook base: {s.TELEGRAM_WEBHOOK_BASE_URL}")
print(f"Mini App: {s.telegram_mini_app_url}")
print("Secrets: configured")
PY

echo "==> Running test suite"
pytest -q

SOCKET_PLACEHOLDER='${DOMAIN_SOCKET}'
COMMAND="/home/${USERNAME}/.virtualenvs/yandex-fleet/bin/uvicorn --app-dir /home/${USERNAME}/Yandex-Fleet-Backend --env-file /home/${USERNAME}/Yandex-Fleet-Backend/.env --uds ${SOCKET_PLACEHOLDER} app.main:app"

if pa website get --domain "${DOMAIN}" >/dev/null 2>&1; then
  echo "==> Site already exists, reloading"
  pa website reload --domain "${DOMAIN}"
else
  echo "==> Creating ASGI site"
  pa website create --domain "${DOMAIN}" --command "${COMMAND}"
fi

echo
echo "Deployment command completed."
echo "Open:"
echo "  https://${DOMAIN}/health/ready"
echo "  https://${DOMAIN}/api/v1/telegram/status"
echo "  https://${DOMAIN}/miniapp/"
echo
echo "If Telegram status is healthy, send /start to the bot."
