# merchant_payout_service

A Django + PostgreSQL merchant payout microservice with a React frontend.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django 4.2, Django REST Framework |
| Database | PostgreSQL 15 |
| Task Queue | Celery + Redis 7 |
| Frontend | React 18, Vite, Tailwind CSS |
| Containerisation | Docker Compose |

## Project Structure

```
merchant_payout_service/
  backend/
    config/          # Django settings, URLs, Celery app
    merchants/       # Merchant app (model, ledger)
    payouts/         # Payout app (model, API, Celery worker)
    manage.py
    Dockerfile
    requirements.txt
  frontend/
    src/
  docker-compose.yml
  .env.example
  README.md
```

## Quick Start

### 1. Copy env file
```bash
cp .env.example .env
# Edit .env and set a strong SECRET_KEY
```

### 2. Start all services
```bash
docker compose up --build
```

| Service | URL |
|---------|-----|
| Django API | http://localhost:8000 |
| React frontend | http://localhost:5173 |
| PostgreSQL | localhost:5432 |
| Redis | localhost:6379 |

### 3. Run migrations (first run)
The backend container automatically runs `migrate` on startup.

To run manually:
```bash
docker compose exec backend python manage.py migrate
```

### 4. Create a superuser
```bash
docker compose exec backend python manage.py createsuperuser
```

## Seed Data

Run the seed command to populate 3 merchants with credit history:

```bash
docker compose exec backend python manage.py seed_merchants
```

## Test Merchant IDs

Use these IDs in the `X-Merchant-Id` header to test the API directly:

| Merchant | Email | ID |
|----------|-------|-----|
| BluePine Logistics | accounts@bluepinelogistics.co.in | a9dc7fb7-116c-415a-8730-444d6e0dc632 |
| Mango Street Foods | finance@mangostreetfoods.com | 48226e65-4fa8-48ef-9029-e0ddc7b407a0 |
| Zephyr Electronics Pvt. Ltd. | payouts@zephyrelectronics.in | 8bd90fe6-0eb6-45c8-8481-43adb48a3aa6 |

## Verify Ledger Integrity

Run this to confirm the invariant: `sum(credits) - sum(debits) = available_balance`

```bash
docker compose exec backend python manage.py verify_ledger_integrity
```

## Running Tests

```bash
docker compose exec backend pytest payouts/tests/ -v
```

## Known Limitations

- **Customer payment flow** is not implemented. Credits are seeded via `seed_merchants` command.
- **Bank settlement** is simulated: 70% success, 20% failure, 10% hung/retry.
- **Idempotency keys** expire after 24 hours (enforced at lookup time).
- **No authentication system** — merchant identity is established via `X-Merchant-Id` header.

## Admin Panel

Access the Django admin at `http://localhost:8000/admin`

Create a superuser first:

```bash
docker compose exec backend python manage.py createsuperuser
```

## Environment Variables

See [`.env.example`](.env.example) for all required variables.

| Variable | Description | Default |
|----------|-------------|---------|
| `SECRET_KEY` | Django secret key | *(required)* |
| `DEBUG` | Debug mode | `True` |
| `ALLOWED_HOSTS` | Comma-separated allowed hosts | `localhost,...` |
| `DATABASE_URL` | PostgreSQL DSN | `postgres://payouts_user:payouts_pass@db:5432/payouts_db` |
| `CELERY_BROKER_URL` | Redis broker URL | `redis://redis:6379/0` |

## Development

### Backend only (no Docker)
```bash
cd backend
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

### Frontend only (no Docker)
```bash
cd frontend
npm install
npm run dev
```

### Run Celery worker locally
```bash
cd backend
celery -A config worker -l info
```
