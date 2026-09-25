# Yandex Fleet Backend

This project provides an MVP backend for integrating with the public Yandex Fleet API.

## What it does

- Reads Yandex Fleet data for drivers, vehicles and orders
- Stores normalized records in PostgreSQL
- Applies order filter rules for each driver
- Exposes REST API for frontend/mobile clients
- Publishes real-time order events via WebSocket/Redis
- Keeps order-offer actions isolated behind an explicit provider interface

## Architecture

- FastAPI application
- SQLAlchemy models and Alembic migrations
- Redis-backed locks and pub/sub
- Service layer for Yandex integration and filtering

## Requirements

- Python 3.12+
- PostgreSQL
- Redis
- Docker + Docker Compose

## Environment setup

Copy the example file and adjust credentials:

```bash
cp .env.example .env
```

## Local run

```bash
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

## Docker run

```bash
docker compose up -d --build
```

## Migrations

```bash
alembic upgrade head
```

## Tests

```bash
pytest -q
```

## Yandex credentials

Get them from your Yandex Fleet project setup or taxi park integration team:

- YANDEX_CLIENT_ID
- YANDEX_API_KEY
- YANDEX_PARK_ID

## Public Fleet API capabilities used

- orders read
- drivers read
- vehicles read
- basic metadata access

## Public Fleet API limitations

The public API does not expose supported methods for:

- accept incoming offer
- reject incoming offer
- skip without activity loss
- neutral skip behaviour in Yandex Activity

This is intentionally isolated behind a provider abstraction and returns an explicit unsupported error instead of a fake success.

## Example curl

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/v1/orders
curl http://localhost:8000/api/v1/integrations/yandex/status
```
