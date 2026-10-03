"""Check Firebase's public signing certificates using the backend auth transport."""

import time

from firebase_admin import auth

from app.config import get_settings
from app.mobile.firebase import firebase_auth_app

CERT_URL = (
    "https://www.googleapis.com/robot/v1/metadata/x509/"
    "securetoken@system.gserviceaccount.com"
)


def main() -> None:
    settings = get_settings()
    app = firebase_auth_app()
    session = auth._get_client(app)._token_verifier.request.session
    started = time.monotonic()
    try:
        response = session.get(CERT_URL, timeout=settings.FIREBASE_HTTP_TIMEOUT_SECONDS)
        response.raise_for_status()
        certs = response.json()
        if not isinstance(certs, dict) or not certs:
            raise ValueError("No Firebase certificates returned")
    except Exception as exc:
        print(f"Firebase certificate check failed: {type(exc).__name__}")
        raise SystemExit(1) from None
    print(
        "Firebase certificates reachable: "
        f"HTTP {response.status_code}, {len(certs)} keys, "
        f"{time.monotonic() - started:.2f}s"
    )


if __name__ == "__main__":
    main()
