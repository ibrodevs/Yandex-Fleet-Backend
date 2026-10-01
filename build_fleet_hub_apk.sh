#!/usr/bin/env bash
set -euo pipefail

API_BASE_URL="https://yandexfeetbackend21.pythonanywhere.com/api/v1/mobile"
HEALTH_URL="https://yandexfeetbackend21.pythonanywhere.com/health"
EXPECTED_PACKAGE="kg.fleethub.driver_app"
EXPECTED_FIREBASE_PROJECT="yandex-fleet"

if [[ -n "${REPO_ROOT:-}" ]]; then
  ROOT="$REPO_ROOT"
elif [[ -f "./mobile/driver_app/pubspec.yaml" ]]; then
  ROOT="$(pwd)"
elif [[ -f "./pubspec.yaml" && "$(basename "$(pwd)")" == "driver_app" ]]; then
  ROOT="$(cd ../.. && pwd)"
else
  echo "ERROR: run from Yandex-Fleet-Backend root or set REPO_ROOT"
  exit 1
fi

APP_DIR="$ROOT/mobile/driver_app"
GOOGLE_JSON="$APP_DIR/android/app/google-services.json"
DIST_DIR="$APP_DIR/dist"

for cmd in flutter python3 curl; do
  command -v "$cmd" >/dev/null 2>&1 || { echo "ERROR: missing $cmd"; exit 1; }
done

if [[ ! -f "$GOOGLE_JSON" ]]; then
  echo "ERROR: missing $GOOGLE_JSON"
  exit 1
fi

python3 - "$GOOGLE_JSON" "$EXPECTED_PACKAGE" "$EXPECTED_FIREBASE_PROJECT" <<'PY'
import json, sys
path, expected_package, expected_project = sys.argv[1:4]
with open(path, encoding="utf-8") as f:
    data = json.load(f)
project_id = str(data.get("project_info", {}).get("project_id", ""))
packages = []
for client in data.get("client", []):
    pkg = client.get("client_info", {}).get("android_client_info", {}).get("package_name")
    if pkg:
        packages.append(str(pkg))
if project_id != expected_project:
    raise SystemExit(f"ERROR: Firebase project_id {project_id!r}, expected {expected_project!r}")
if expected_package not in packages:
    raise SystemExit(f"ERROR: package {expected_package!r} not found in {packages!r}")
print("OK Firebase project:", project_id)
print("OK Android package:", expected_package)
PY

echo "Checking backend..."
curl -fsS --connect-timeout 10 --max-time 20 "$HEALTH_URL"
echo

cd "$APP_DIR"
flutter --version
flutter clean
flutter pub get
flutter analyze
flutter test

mkdir -p "$DIST_DIR"

flutter build apk --debug --dart-define=API_BASE_URL="$API_BASE_URL"
cp -f build/app/outputs/flutter-apk/app-debug.apk "$DIST_DIR/fleet-hub-debug.apk"

flutter build apk --release --dart-define=API_BASE_URL="$API_BASE_URL"
cp -f build/app/outputs/flutter-apk/app-release.apk "$DIST_DIR/fleet-hub-release.apk"

echo
echo "SUCCESS"
echo "Debug:   $DIST_DIR/fleet-hub-debug.apk"
echo "Release: $DIST_DIR/fleet-hub-release.apk"
echo
echo "For login diagnostics install debug first:"
echo "adb install -r \"$DIST_DIR/fleet-hub-debug.apk\""
echo "Then run: flutter logs"

if [[ "${INSTALL:-0}" == "1" ]]; then
  command -v adb >/dev/null 2>&1 || { echo "ERROR: adb not found"; exit 1; }
  adb get-state >/dev/null 2>&1 || { echo "ERROR: no authorized adb device"; exit 1; }
  adb install -r "$DIST_DIR/fleet-hub-debug.apk"
fi
