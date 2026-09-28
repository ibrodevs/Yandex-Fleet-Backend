import os

# Unit tests must never inherit production-like Yandex credentials/mode from a
# developer's local .env and make live Fleet API requests during collection.
os.environ["YANDEX_MOCK_MODE"] = "true"
