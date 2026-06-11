"""API endpoint tests using mocked service layer."""
import io
import uuid
import wave
from unittest.mock import MagicMock, patch

import pytest
import torch
from django.core.files.uploadedfile import InMemoryUploadedFile
from rest_framework.test import APIClient


def _make_uploaded_wav(duration_s: int = 1) -> InMemoryUploadedFile:
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x01" * 16000 * duration_s)
    raw = buf.getvalue()
    return InMemoryUploadedFile(
        file=io.BytesIO(raw),
        field_name="audio_file",
        name="test.wav",
        content_type="audio/wav",
        size=len(raw),
        charset=None,
    )


@pytest.fixture
def client():
    return APIClient()


# ---------------------------------------------------------------------------
# POST /api/watermark/verify/
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestVerifyWatermarkView:
    BASE_URL = "/api/watermark/verify/"

    def _mock_services(self, detected: bool, registry_entry=None):
        """Return a context manager stack that mocks all service calls."""
        from apps.watermark.domain.entities import WatermarkPayload

        audio_tensor = torch.zeros(1, 1, 16000)
        file_bytes = b"fake_bytes"
        payload = (
            WatermarkPayload(
                binary="1010011110101011",
                integer=42923,
                hex_value="A7AB",
                confidence=0.998,
            )
            if detected
            else None
        )
        confidence = 0.998 if detected else 0.05

        return {
            "audio_tensor": audio_tensor,
            "file_bytes": file_bytes,
            "payload": payload,
            "confidence": confidence,
            "registry_entry": registry_entry,
        }

    def test_no_watermark_returns_200(self, client):
        from apps.watermark.models import WatermarkAuditLog
        ctx = self._mock_services(detected=False)

        with patch("apps.watermark.api.views._audio_loader.load", return_value=(ctx["audio_tensor"], ctx["file_bytes"])), \
             patch("apps.watermark.api.views._detector.detect", return_value=(ctx["confidence"], None)), \
             patch("apps.watermark.api.views._audit_svc.record", return_value=MagicMock(id=uuid.uuid4())):

            resp = client.post(self.BASE_URL, {"audio_file": _make_uploaded_wav()}, format="multipart")

        assert resp.status_code == 200
        data = resp.json()
        assert data["watermark_detected"] is False
        assert data["binary_message"] is None
        assert data["ownership_verified"] is False

    def test_detected_with_owner_returns_200(self, client):
        from apps.watermark.domain.entities import WatermarkPayload

        payload = WatermarkPayload(binary="1010011110101011", integer=42923, hex_value="A7AB", confidence=0.998)
        registry = MagicMock()
        registry.copyright_name = "TVD COPYRIGHT"
        registry.company_name = "TVD Technologies"
        registry.owner_name = "TVD Media Pvt Ltd"
        registry.contact_email = "legal@tvd.com"
        audit_mock = MagicMock(id=uuid.uuid4())

        with patch("apps.watermark.api.views._audio_loader.load", return_value=(torch.zeros(1,1,100), b"bytes")), \
             patch("apps.watermark.api.views._detector.detect", return_value=(0.998, torch.ones(1, 16))), \
             patch("apps.watermark.api.views._decoder.decode", return_value=payload), \
             patch("apps.watermark.api.views._registry_svc.lookup_by_integer", return_value=registry), \
             patch("apps.watermark.api.views._audit_svc.record", return_value=audit_mock):

            resp = client.post(self.BASE_URL, {"audio_file": _make_uploaded_wav()}, format="multipart")

        assert resp.status_code == 200
        data = resp.json()
        assert data["watermark_detected"] is True
        assert data["ownership_verified"] is True
        assert data["owner"]["copyright_name"] == "TVD COPYRIGHT"
        assert data["binary_message"] == "1010011110101011"
        assert data["integer_message"] == 42923
        assert data["hex_message"] == "A7AB"

    def test_detected_no_owner_returns_200(self, client):
        from apps.watermark.domain.entities import WatermarkPayload

        payload = WatermarkPayload(binary="1010011110101011", integer=42923, hex_value="A7AB", confidence=0.995)

        with patch("apps.watermark.api.views._audio_loader.load", return_value=(torch.zeros(1,1,100), b"bytes")), \
             patch("apps.watermark.api.views._detector.detect", return_value=(0.995, torch.ones(1, 16))), \
             patch("apps.watermark.api.views._decoder.decode", return_value=payload), \
             patch("apps.watermark.api.views._registry_svc.lookup_by_integer", return_value=None), \
             patch("apps.watermark.api.views._audit_svc.record", return_value=MagicMock(id=uuid.uuid4())):

            resp = client.post(self.BASE_URL, {"audio_file": _make_uploaded_wav()}, format="multipart")

        assert resp.status_code == 200
        data = resp.json()
        assert data["watermark_detected"] is True
        assert data["ownership_verified"] is False
        assert data["owner"] is None

    def test_missing_audio_file_returns_400(self, client):
        resp = client.post(self.BASE_URL, {}, format="multipart")
        assert resp.status_code == 400

    def test_invalid_extension_returns_400(self, client):
        f = InMemoryUploadedFile(
            io.BytesIO(b"data"),
            "audio_file",
            "file.exe",
            "application/octet-stream",
            4,
            None,
        )
        resp = client.post(self.BASE_URL, {"audio_file": f}, format="multipart")
        assert resp.status_code == 400

    def test_audio_too_large_returns_413(self, client):
        from core.exceptions import AudioTooLargeError
        with patch("apps.watermark.api.views._audio_loader.load", side_effect=AudioTooLargeError("too big")):
            resp = client.post(self.BASE_URL, {"audio_file": _make_uploaded_wav()}, format="multipart")
        assert resp.status_code == 413

    def test_corrupted_audio_returns_422(self, client):
        from core.exceptions import CorruptedAudioError
        with patch("apps.watermark.api.views._audio_loader.load", side_effect=CorruptedAudioError("corrupt")):
            resp = client.post(self.BASE_URL, {"audio_file": _make_uploaded_wav()}, format="multipart")
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# POST /api/watermark/register/
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestRegisterWatermarkView:
    BASE_URL = "/api/watermark/register/"
    VALID_PAYLOAD = {
        "watermark_binary": "1010011110101011",
        "copyright_name": "TVD COPYRIGHT",
        "company_name": "TVD Technologies",
        "owner_name": "TVD Media Pvt Ltd",
        "contact_email": "legal@tvd.com",
    }

    def test_register_success_returns_201(self, client):
        from apps.watermark.models import WatermarkRegistry
        resp = client.post(self.BASE_URL, self.VALID_PAYLOAD, format="json")
        assert resp.status_code == 201
        data = resp.json()
        assert data["watermark_binary"] == "1010011110101011"
        assert data["watermark_integer"] == 42923
        assert data["watermark_hex"] == "A7AB"

    def test_register_duplicate_returns_409(self, client):
        client.post(self.BASE_URL, self.VALID_PAYLOAD, format="json")
        resp = client.post(self.BASE_URL, self.VALID_PAYLOAD, format="json")
        assert resp.status_code == 409

    def test_register_invalid_binary_returns_400(self, client):
        payload = {**self.VALID_PAYLOAD, "watermark_binary": "XXXXXXXXXXXXXXXX"}
        resp = client.post(self.BASE_URL, payload, format="json")
        assert resp.status_code == 400

    def test_register_short_binary_returns_400(self, client):
        payload = {**self.VALID_PAYLOAD, "watermark_binary": "1010"}
        resp = client.post(self.BASE_URL, payload, format="json")
        assert resp.status_code == 400

    def test_register_missing_fields_returns_400(self, client):
        resp = client.post(self.BASE_URL, {"watermark_binary": "1010011110101011"}, format="json")
        assert resp.status_code == 400


# ---------------------------------------------------------------------------
# GET /api/watermark/lookup/<int>/
# ---------------------------------------------------------------------------
@pytest.mark.django_db
class TestLookupWatermarkView:
    def test_lookup_found_returns_200(self, client):
        from apps.watermark.models import WatermarkRegistry
        WatermarkRegistry.objects.create(
            watermark_binary="1010011110101011",
            watermark_integer=42923,
            copyright_name="TVD COPYRIGHT",
            company_name="TVD Technologies",
            owner_name="TVD Media Pvt Ltd",
            contact_email="legal@tvd.com",
        )
        resp = client.get("/api/watermark/lookup/42923/")
        assert resp.status_code == 200
        data = resp.json()
        assert data["watermark_integer"] == 42923
        assert data["owner"]["copyright_name"] == "TVD COPYRIGHT"

    def test_lookup_not_found_returns_404(self, client):
        resp = client.get("/api/watermark/lookup/99999/")
        assert resp.status_code == 404
