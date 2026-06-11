"""Shared test fixtures."""
import io
import wave

import pytest
from django.core.files.uploadedfile import InMemoryUploadedFile
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def minimal_wav_bytes() -> bytes:
    """Generate a valid 1-second 16kHz mono WAV file in memory."""
    buf = io.BytesIO()
    with wave.open(buf, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(16000)
        wf.writeframes(b"\x00\x01" * 16000)  # 1 second of near-silence
    return buf.getvalue()


@pytest.fixture
def uploaded_wav(minimal_wav_bytes: bytes) -> InMemoryUploadedFile:
    return InMemoryUploadedFile(
        file=io.BytesIO(minimal_wav_bytes),
        field_name="audio_file",
        name="test.wav",
        content_type="audio/wav",
        size=len(minimal_wav_bytes),
        charset=None,
    )


@pytest.fixture
def registry_data() -> dict:
    return {
        "watermark_binary": "1010011110101011",
        "watermark_integer": 42923,
        "watermark_hex": "A7AB",
        "copyright_name": "TVD COPYRIGHT",
        "company_name": "TVD Technologies",
        "owner_name": "TVD Media Pvt Ltd",
        "contact_email": "legal@tvd.com",
        "notes": "",
    }
