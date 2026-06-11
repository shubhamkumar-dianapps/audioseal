# CLAUDE.md — AudioSeal Watermark Verification Service

## Project Purpose

Production-grade Django service for copyright ownership verification. Every distributed audio file contains an AudioSeal 16-bit watermark. This service detects those watermarks, decodes the embedded identifier, and maps it to a registered copyright owner.

## Tech Stack

- **Python 3.11+** / **Django 5** / **Django REST Framework**
- **PostgreSQL** — primary database
- **AudioSeal 0.2.0** — watermark detection model (Facebook Research)
- **PyTorch** / **torchaudio** — audio processing
- **structlog** — structured JSON logging
- **pytest-django** / **factory-boy** — testing

## Project Structure

```
core/           Django project settings, logging, exceptions, root URLs
apps/
  watermark/
    domain/     Pure Python value objects (entities, DTOs, enums) — no Django imports
    models.py   WatermarkRegistry + WatermarkAuditLog ORM models
    repositories/  ORM access layer — isolates queries from business logic
    services/   Business logic: audio_loader, detector, decoder, registry, audit
    api/        DRF serializers, views, URL patterns
    tests/      pytest test suite
```

## Local Setup

```bash
# 1. Create and activate virtual environment
python -m venv .venv && source .venv/bin/activate

# 2. Install dependencies (CPU-only torch for development)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -e ".[dev]"

# 3. Configure environment
cp .env.example .env
# Edit .env with your database credentials

# 4. Run migrations
python manage.py migrate

# 5. Create a superuser (optional)
python manage.py createsuperuser

# 6. Run development server
python manage.py runserver
```

## Database

SQLite is used automatically in local development when `DB_PASSWORD` is not set (see `core/settings/local.py`). For full PostgreSQL:

```bash
createdb audioseal_db
createuser audioseal_user
psql -c "GRANT ALL ON DATABASE audioseal_db TO audioseal_user;"
```

## API Endpoints

### Verify Watermark
```bash
curl -X POST \
  -F "audio_file=@leaked_song.mp3" \
  http://localhost:8000/api/watermark/verify/
```

### Register Ownership
```bash
curl -X POST \
  -H "Content-Type: application/json" \
  -d '{
    "watermark_binary": "1010011110101011",
    "copyright_name": "TVD COPYRIGHT",
    "company_name": "TVD Technologies",
    "owner_name": "TVD Media Pvt Ltd",
    "contact_email": "legal@tvd.com"
  }' \
  http://localhost:8000/api/watermark/register/
```

### Lookup by Integer
```bash
curl http://localhost:8000/api/watermark/lookup/42923/
```

### Audit Log
```bash
curl http://localhost:8000/api/watermark/audit/
```

## Running Tests

```bash
# All tests
pytest

# With coverage report
coverage run -m pytest
coverage report

# Specific module
pytest apps/watermark/tests/test_services.py -v

# Skip DB tests (fast unit tests only)
pytest apps/watermark/tests/test_services.py -v
```

## Key Architectural Decisions

| Decision | Rationale |
|----------|-----------|
| Singleton detector (`AudioSealDetectorService._detector`) | Model loads once per process; ~200MB weights, 2–5s load time |
| BytesIO throughout (`AudioLoaderService`) | No temp files → no path traversal risk |
| `SET_NULL` on audit log FK | Deleting a registry entry preserves audit history for legal use |
| No `updated_at` on `WatermarkAuditLog` | Enforces immutability — audit records are append-only |
| `WatermarkRegistry.save()` derives `watermark_hex` | Keeps hex consistent even if only integer is updated |
| `AppConfig.ready()` pre-loads detector | Avoids cold-start latency on the first API request |
| Repository pattern | Isolates ORM from business logic — makes service tests mockable |

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `SECRET_KEY` | *(required in prod)* | Django secret key |
| `DEBUG` | `False` | Enable debug mode |
| `DB_PASSWORD` | *(required for PG)* | PostgreSQL password |
| `AUDIOSEAL_DEVICE` | `cpu` | `cpu` or `cuda` |
| `WATERMARK_DETECTION_THRESHOLD` | `0.5` | Confidence cutoff for detection |
| `AUDIOSEAL_MODEL_CARD` | `audioseal_detector_16bits` | AudioSeal model identifier |

## Docker

```bash
# Start all services
cp .env.example .env && docker compose up --build

# Run migrations
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser
```
