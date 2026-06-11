# AudioSeal Watermark Verification & Copyright Ownership Service

A production-grade Django REST API that detects [AudioSeal](https://github.com/facebookresearch/audioseal) watermarks in audio files, extracts the embedded 16-bit identifier, and maps it to registered copyright ownership records.

## Business Purpose

When a leaked or suspicious audio file is uploaded, the system:
1. Detects whether an AudioSeal watermark exists
2. Extracts the embedded 16-bit message
3. Converts it to binary, integer, and hex
4. Looks up the watermark in the copyright registry
5. Returns ownership information suitable for legal review
6. Creates an immutable audit trail

---

## Architecture

```
POST audio → AudioLoaderService → AudioSealDetectorService → DecoderService
                                                                    ↓
                                              RegistryService ← WatermarkPayload
                                                    ↓
                                              AuditService → WatermarkAuditLog
                                                    ↓
                                              JSON Response
```

**Key design principles:**
- No business logic in views — pure orchestration
- Repository pattern isolates ORM from services
- AudioSeal model loaded once at startup (singleton)
- All audio processing in-memory via BytesIO
- Immutable audit logs for legal compliance

---

## Installation

### Prerequisites
- Python 3.11+
- PostgreSQL 14+ (or SQLite for local dev)

### Local Setup

```bash
git clone <repo>
cd audio-masking

python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# Install CPU-only PyTorch (faster install, sufficient for dev)
pip install torch torchaudio --index-url https://download.pytorch.org/whl/cpu

# Install project dependencies
pip install -e ".[dev]"

# Configure environment
cp .env.example .env
# Edit .env — set DB credentials or leave DB_PASSWORD empty for SQLite

# Run migrations
python manage.py migrate

# Start server
python manage.py runserver
```

The service is now available at `http://localhost:8000`.

---

## Database Migrations

```bash
# Generate migrations (after model changes)
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Show migration status
python manage.py showmigrations
```

---

## Creating Registry Records

### Via API
```bash
curl -X POST http://localhost:8000/api/watermark/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "watermark_binary": "1010011110101011",
    "copyright_name": "TVD COPYRIGHT",
    "company_name": "TVD Technologies",
    "owner_name": "TVD Media Pvt Ltd",
    "contact_email": "legal@tvd.com",
    "notes": "Album: Midnight Sessions 2024"
  }'
```

### Via Django Admin
Navigate to `http://localhost:8000/admin/` and use the **Watermark Registry** section.

### Via Django Shell
```python
python manage.py shell

from apps.watermark.models import WatermarkRegistry
WatermarkRegistry.objects.create(
    watermark_binary="1010011110101011",
    watermark_integer=42923,
    copyright_name="TVD COPYRIGHT",
    owner_name="TVD Media Pvt Ltd",
    contact_email="legal@tvd.com",
)
```

---

## API Reference

### POST `/api/watermark/verify/`

Verify whether an audio file contains a registered watermark.

**Request:**
```bash
curl -X POST http://localhost:8000/api/watermark/verify/ \
  -F "audio_file=@leaked_song.mp3"
```

**Response — Watermark detected, owner found (HTTP 200):**
```json
{
  "watermark_detected": true,
  "confidence": 0.998,
  "binary_message": "1010011110101011",
  "integer_message": 42923,
  "hex_message": "A7AB",
  "ownership_verified": true,
  "owner": {
    "copyright_name": "TVD COPYRIGHT",
    "company_name": "TVD Technologies",
    "owner_name": "TVD Media Pvt Ltd",
    "contact_email": "legal@tvd.com"
  },
  "audit_id": "550e8400-e29b-41d4-a716-446655440000"
}
```

**Response — Watermark detected, unregistered (HTTP 200):**
```json
{
  "watermark_detected": true,
  "confidence": 0.995,
  "binary_message": "1010011110101011",
  "integer_message": 42923,
  "hex_message": "A7AB",
  "ownership_verified": false,
  "owner": null,
  "audit_id": "..."
}
```

**Response — No watermark (HTTP 200):**
```json
{
  "watermark_detected": false,
  "confidence": 0.11,
  "binary_message": null,
  "integer_message": null,
  "hex_message": null,
  "ownership_verified": false,
  "owner": null,
  "audit_id": "..."
}
```

**Error responses:**
| Status | Code | Meaning |
|--------|------|---------|
| 400 | `VALIDATION_ERROR` | Missing or invalid audio_file field |
| 413 | `AUDIO_TOO_LARGE` | File exceeds 50 MB |
| 415 | `UNSUPPORTED_AUDIO_FORMAT` | Extension/format not supported |
| 422 | `CORRUPTED_AUDIO` | File could not be decoded |

---

### POST `/api/watermark/register/`

Register a new copyright ownership record.

**Request:**
```bash
curl -X POST http://localhost:8000/api/watermark/register/ \
  -H "Content-Type: application/json" \
  -d '{
    "watermark_binary": "1010011110101011",
    "copyright_name": "TVD COPYRIGHT",
    "company_name": "TVD Technologies",
    "owner_name": "TVD Media Pvt Ltd",
    "contact_email": "legal@tvd.com"
  }'
```

**Response (HTTP 201):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "watermark_binary": "1010011110101011",
  "watermark_integer": 42923,
  "watermark_hex": "A7AB",
  "copyright_name": "TVD COPYRIGHT",
  "company_name": "TVD Technologies",
  "owner_name": "TVD Media Pvt Ltd",
  "contact_email": "legal@tvd.com",
  "created_at": "2024-01-15T10:30:00Z"
}
```

**Validation rules:**
- `watermark_binary`: exactly 16 characters, only `0` and `1`
- `contact_email`: valid email format
- `watermark_binary` must be unique

---

### GET `/api/watermark/lookup/<watermark_integer>/`

Look up ownership metadata for a watermark integer value.

```bash
curl http://localhost:8000/api/watermark/lookup/42923/
```

**Response (HTTP 200):**
```json
{
  "watermark_integer": 42923,
  "watermark_binary": "1010011110101011",
  "watermark_hex": "A7AB",
  "owner": {
    "copyright_name": "TVD COPYRIGHT",
    "company_name": "TVD Technologies",
    "owner_name": "TVD Media Pvt Ltd",
    "contact_email": "legal@tvd.com"
  },
  "registered_at": "2024-01-15T10:30:00Z"
}
```

---

### GET `/api/watermark/audit/`

List recent verification audit logs (last 50).

```bash
curl http://localhost:8000/api/watermark/audit/
```

---

## Running Tests

```bash
# Full test suite
pytest

# With coverage
coverage run -m pytest && coverage report

# Only unit tests (no DB required)
pytest apps/watermark/tests/test_services.py -v

# Verbose with output
pytest -v -s
```

---

## Docker

```bash
# Build and start all services
cp .env.example .env
# Edit .env — set DB_PASSWORD

docker compose up --build

# Apply migrations
docker compose exec web python manage.py migrate

# Create admin superuser
docker compose exec web python manage.py createsuperuser
```

The service will be available at `http://localhost:8000`.

---

## Supported Audio Formats

| Format | Extension |
|--------|-----------|
| WAV | `.wav` |
| MP3 | `.mp3` |
| FLAC | `.flac` |
| M4A | `.m4a` |
| OGG | `.ogg` |

**Limits:** 50 MB file size, 10 minutes duration.

---

## Troubleshooting

**`audioseal` model download fails on first request:**
The AudioSeal detector weights (~85 MB) are downloaded from HuggingFace Hub on first use. Ensure outbound internet access or pre-download:
```python
from audioseal import AudioSeal
AudioSeal.load_detector("audioseal_detector_16bits")
```

**`psycopg2` install fails:**
Install system PostgreSQL client libraries:
```bash
# Ubuntu/Debian
sudo apt-get install libpq-dev
# macOS
brew install postgresql
```

**SQLite for local dev:**
If `DB_PASSWORD` is not set in `.env`, the local settings automatically use SQLite (`db.sqlite3`). No PostgreSQL needed for development or testing.

**Confidence always low:**
The detection threshold defaults to `0.5`. A file without an AudioSeal watermark embedded using the `audioseal_wm_16bits` generator will score near 0. Use only files watermarked with AudioSeal.

---

## Database Schema

### `watermark_registry`
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `watermark_binary` | varchar(16) | Unique 16-bit binary string |
| `watermark_integer` | integer | Unique, 0–65535 |
| `watermark_hex` | varchar(8) | Derived from integer on save |
| `copyright_name` | varchar(255) | Legal copyright holder |
| `company_name` | varchar(255) | Organisation name |
| `owner_name` | varchar(255) | Contact person |
| `contact_email` | varchar(254) | Legal enquiries email |
| `created_at` | timestamptz | Auto |
| `updated_at` | timestamptz | Auto |

### `watermark_audit_log`
| Column | Type | Notes |
|--------|------|-------|
| `id` | UUID | Primary key |
| `uploaded_file_name` | varchar(500) | Original filename |
| `uploaded_file_hash` | varchar(64) | SHA-256 of uploaded bytes |
| `watermark_detected` | boolean | True if above threshold |
| `confidence_score` | float | 0.0–1.0 |
| `extracted_binary` | varchar(16) | Nullable |
| `extracted_integer` | integer | Nullable |
| `matched_registry_id` | UUID FK | SET NULL on registry delete |
| `processing_time_ms` | integer | Wall-clock ms |
| `created_at` | timestamptz | Immutable — no updated_at |
