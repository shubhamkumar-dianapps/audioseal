"""Unit tests for service layer — minimal Django dependency."""
import io
import wave
from unittest.mock import MagicMock, patch

import pytest
import torch

from apps.watermark.domain.entities import WatermarkPayload
from apps.watermark.services.decoder_service import DecoderService


# ---------------------------------------------------------------------------
# DecoderService — pure unit tests, no mocks required
# ---------------------------------------------------------------------------
class TestDecoderService:
    def setup_method(self):
        self.svc = DecoderService()

    def test_decode_known_bits_returns_correct_payload(self):
        bits = [1, 0, 1, 0, 0, 1, 1, 1, 1, 0, 1, 0, 1, 0, 1, 1]
        message = torch.tensor([bits], dtype=torch.float32)
        result = self.svc.decode(0.998, message)

        assert result is not None
        assert result.binary == "1010011110101011"
        assert result.integer == 42923
        assert result.hex_value == "A7AB"
        assert result.confidence == pytest.approx(0.998)

    def test_decode_none_message_returns_none(self):
        assert self.svc.decode(0.3, None) is None

    def test_decode_all_zeros(self):
        message = torch.zeros(1, 16)
        result = self.svc.decode(0.9, message)
        assert result is not None
        assert result.binary == "0000000000000000"
        assert result.integer == 0
        assert result.hex_value == "0000"

    def test_decode_all_ones(self):
        message = torch.ones(1, 16)
        result = self.svc.decode(0.9, message)
        assert result is not None
        assert result.integer == 65535
        assert result.hex_value == "FFFF"

    def test_decode_hex_zero_padded(self):
        bits = [0] * 15 + [1]  # integer = 1
        message = torch.tensor([bits], dtype=torch.float32)
        result = self.svc.decode(0.9, message)
        assert result is not None
        assert result.hex_value == "0001"

    def test_payload_is_frozen(self):
        bits = [1] * 16
        message = torch.tensor([bits], dtype=torch.float32)
        result = self.svc.decode(0.9, message)
        with pytest.raises((TypeError, AttributeError)):
            result.binary = "changed"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# AudioLoaderService
# ---------------------------------------------------------------------------
class TestAudioLoaderService:
    def _make_wav_bytes(self, channels=1, sample_rate=16000, duration_s=1) -> bytes:
        buf = io.BytesIO()
        with wave.open(buf, "wb") as wf:
            wf.setnchannels(channels)
            wf.setsampwidth(2)
            wf.setframerate(sample_rate)
            wf.writeframes(b"\x00\x01" * sample_rate * duration_s * channels)
        return buf.getvalue()

    def _make_uploaded_file(self, data: bytes, name: str = "test.wav", content_type: str = "audio/wav"):
        from django.core.files.uploadedfile import InMemoryUploadedFile
        return InMemoryUploadedFile(
            file=io.BytesIO(data),
            field_name="audio_file",
            name=name,
            content_type=content_type,
            size=len(data),
            charset=None,
        )

    def test_load_valid_wav_returns_tensor_and_bytes(self):
        from apps.watermark.services.audio_loader import AudioLoaderService
        wav_bytes = self._make_wav_bytes()
        f = self._make_uploaded_file(wav_bytes)
        svc = AudioLoaderService()
        tensor, raw = svc.load(f)
        assert isinstance(tensor, torch.Tensor)
        assert tensor.ndim == 3
        assert tensor.shape[0] == 1  # batch
        assert tensor.shape[1] == 1  # mono
        assert isinstance(raw, bytes)
        assert raw == wav_bytes

    def test_load_rejects_oversized_file(self):
        from apps.watermark.services.audio_loader import AudioLoaderService
        from core.exceptions import AudioTooLargeError
        from django.test import override_settings

        wav_bytes = self._make_wav_bytes()
        f = self._make_uploaded_file(wav_bytes)
        # File is ~32KB; set limit to 10 bytes to force rejection
        with override_settings(AUDIOSEAL_MAX_FILE_BYTES=10):
            with pytest.raises(AudioTooLargeError):
                AudioLoaderService().load(f)

    def test_load_rejects_wrong_extension(self):
        from apps.watermark.services.audio_loader import AudioLoaderService
        from core.exceptions import UnsupportedAudioFormatError
        wav_bytes = self._make_wav_bytes()
        f = self._make_uploaded_file(wav_bytes, name="test.exe")
        with pytest.raises(UnsupportedAudioFormatError):
            AudioLoaderService().load(f)

    def test_load_rejects_bad_magic_bytes(self):
        from apps.watermark.services.audio_loader import AudioLoaderService
        from core.exceptions import UnsupportedAudioFormatError
        f = self._make_uploaded_file(b"not audio at all" * 100, name="test.wav")
        with pytest.raises(UnsupportedAudioFormatError):
            AudioLoaderService().load(f)

    def test_load_rejects_corrupted_audio(self):
        import struct

        from apps.watermark.services.audio_loader import AudioLoaderService
        from core.exceptions import CorruptedAudioError, UnsupportedAudioFormatError

        # Build a WAV header with wrong data size to corrupt the file
        corrupted = b"RIFF" + struct.pack("<I", 36) + b"WAVE" + b"\x00" * 20
        f = self._make_uploaded_file(corrupted, name="bad.wav")
        with pytest.raises((UnsupportedAudioFormatError, CorruptedAudioError)):
            AudioLoaderService().load(f)

    def test_load_stereo_converted_to_mono(self):
        from apps.watermark.services.audio_loader import AudioLoaderService
        wav_bytes = self._make_wav_bytes(channels=2)
        f = self._make_uploaded_file(wav_bytes)
        svc = AudioLoaderService()
        tensor, _ = svc.load(f)
        assert tensor.shape[1] == 1  # mono after conversion

    def test_load_normalises_amplitude(self):
        from apps.watermark.services.audio_loader import AudioLoaderService
        wav_bytes = self._make_wav_bytes()
        f = self._make_uploaded_file(wav_bytes)
        tensor, _ = AudioLoaderService().load(f)
        assert tensor.abs().max().item() <= 1.0 + 1e-5


# ---------------------------------------------------------------------------
# RegistryService
# ---------------------------------------------------------------------------
class TestRegistryService:
    def _make_svc(self):
        from apps.watermark.services.registry_service import RegistryService
        repo = MagicMock()
        return RegistryService(repo), repo

    def test_register_valid_binary(self):
        from apps.watermark.domain.dto import RegistryCreateDTO
        svc, repo = self._make_svc()
        repo.exists_binary.return_value = False
        repo.create.return_value = MagicMock(
            watermark_binary="1010011110101011",
            watermark_integer=42923,
        )
        dto = RegistryCreateDTO(
            watermark_binary="1010011110101011",
            copyright_name="Test Corp",
            company_name="Test",
            owner_name="Alice",
            contact_email="alice@test.com",
        )
        result = svc.register(dto)
        repo.create.assert_called_once()
        call_kwargs = repo.create.call_args[1]
        assert call_kwargs["watermark_integer"] == 42923
        assert call_kwargs["watermark_hex"] == "A7AB"

    def test_register_invalid_binary_raises(self):
        from apps.watermark.domain.dto import RegistryCreateDTO
        from core.exceptions import InvalidWatermarkBinaryError
        svc, _ = self._make_svc()
        dto = RegistryCreateDTO(
            watermark_binary="10100111XXXXXXXX",  # invalid chars
            copyright_name="X",
            company_name="",
            owner_name="X",
            contact_email="x@x.com",
        )
        with pytest.raises(InvalidWatermarkBinaryError):
            svc.register(dto)

    def test_register_too_short_raises(self):
        from apps.watermark.domain.dto import RegistryCreateDTO
        from core.exceptions import InvalidWatermarkBinaryError
        svc, _ = self._make_svc()
        dto = RegistryCreateDTO(
            watermark_binary="101",
            copyright_name="X",
            company_name="",
            owner_name="X",
            contact_email="x@x.com",
        )
        with pytest.raises(InvalidWatermarkBinaryError):
            svc.register(dto)

    def test_register_duplicate_raises(self):
        from apps.watermark.domain.dto import RegistryCreateDTO
        from core.exceptions import WatermarkAlreadyExistsError
        svc, repo = self._make_svc()
        repo.exists_binary.return_value = True
        dto = RegistryCreateDTO(
            watermark_binary="1010011110101011",
            copyright_name="X",
            company_name="",
            owner_name="X",
            contact_email="x@x.com",
        )
        with pytest.raises(WatermarkAlreadyExistsError):
            svc.register(dto)

    def test_lookup_returns_none_when_not_found(self):
        svc, repo = self._make_svc()
        repo.find_by_integer.return_value = None
        assert svc.lookup_by_integer(42923) is None

    def test_get_or_404_raises_when_not_found(self):
        from core.exceptions import WatermarkNotFoundError
        svc, repo = self._make_svc()
        repo.find_by_integer.return_value = None
        with pytest.raises(WatermarkNotFoundError):
            svc.get_or_404(42923)


# ---------------------------------------------------------------------------
# AuditService
# ---------------------------------------------------------------------------
class TestAuditService:
    def test_record_computes_sha256(self):
        import hashlib

        from apps.watermark.services.audit_service import AuditService

        repo = MagicMock()
        repo.create.return_value = MagicMock(id="fake-uuid")
        svc = AuditService(repo)
        file_bytes = b"hello audio"
        svc.record(
            file_name="test.wav",
            file_bytes=file_bytes,
            payload=None,
            registry_match=None,
            processing_ms=42,
            confidence_score=0.1,
        )
        expected_hash = hashlib.sha256(file_bytes).hexdigest()
        repo.create.assert_called_once()
        assert repo.create.call_args[1]["uploaded_file_hash"] == expected_hash

    def test_record_detected_sets_fields(self):
        from apps.watermark.domain.entities import WatermarkPayload
        from apps.watermark.services.audit_service import AuditService

        repo = MagicMock()
        repo.create.return_value = MagicMock(id="x")
        svc = AuditService(repo)
        payload = WatermarkPayload(binary="1010011110101011", integer=42923, hex_value="A7AB", confidence=0.9)
        svc.record(
            file_name="f.wav",
            file_bytes=b"data",
            payload=payload,
            registry_match=None,
            processing_ms=10,
            confidence_score=0.9,
        )
        kwargs = repo.create.call_args[1]
        assert kwargs["watermark_detected"] is True
        assert kwargs["extracted_binary"] == "1010011110101011"
        assert kwargs["extracted_integer"] == 42923
