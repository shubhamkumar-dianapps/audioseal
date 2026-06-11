"""Model tests — require database."""
import pytest

from apps.watermark.models import WatermarkAuditLog, WatermarkRegistry


@pytest.mark.django_db
class TestWatermarkRegistry:
    def test_save_derives_hex_from_integer(self):
        entry = WatermarkRegistry.objects.create(
            watermark_binary="1010011110101011",
            watermark_integer=42923,
            copyright_name="TVD",
            owner_name="Alice",
            contact_email="alice@tvd.com",
        )
        assert entry.watermark_hex == "A7AB"

    def test_hex_updated_on_save(self):
        entry = WatermarkRegistry.objects.create(
            watermark_binary="0000000000000001",
            watermark_integer=1,
            copyright_name="Test",
            owner_name="Bob",
            contact_email="bob@test.com",
        )
        assert entry.watermark_hex == "0001"

    def test_str_representation(self):
        entry = WatermarkRegistry(watermark_hex="A7AB", copyright_name="TVD")
        assert "A7AB" in str(entry)
        assert "TVD" in str(entry)

    def test_watermark_binary_unique(self):
        from django.db import IntegrityError

        WatermarkRegistry.objects.create(
            watermark_binary="1111000011110000",
            watermark_integer=61680,
            copyright_name="A",
            owner_name="A",
            contact_email="a@a.com",
        )
        with pytest.raises(IntegrityError):
            WatermarkRegistry.objects.create(
                watermark_binary="1111000011110000",
                watermark_integer=61681,  # different int but same binary
                copyright_name="B",
                owner_name="B",
                contact_email="b@b.com",
            )


@pytest.mark.django_db
class TestWatermarkAuditLog:
    def _create_registry(self):
        return WatermarkRegistry.objects.create(
            watermark_binary="1010011110101011",
            watermark_integer=42923,
            copyright_name="TVD",
            owner_name="Alice",
            contact_email="alice@tvd.com",
        )

    def test_audit_log_created_with_registry(self):
        registry = self._create_registry()
        log = WatermarkAuditLog.objects.create(
            uploaded_file_name="test.wav",
            uploaded_file_hash="a" * 64,
            watermark_detected=True,
            confidence_score=0.99,
            extracted_binary="1010011110101011",
            extracted_integer=42923,
            matched_registry=registry,
            processing_time_ms=150,
        )
        assert log.matched_registry == registry
        assert log.watermark_detected is True

    def test_registry_deletion_nullifies_fk(self):
        registry = self._create_registry()
        log = WatermarkAuditLog.objects.create(
            uploaded_file_name="test.wav",
            uploaded_file_hash="b" * 64,
            watermark_detected=True,
            confidence_score=0.9,
            extracted_binary="1010011110101011",
            extracted_integer=42923,
            matched_registry=registry,
            processing_time_ms=100,
        )
        registry.delete()
        log.refresh_from_db()
        assert log.matched_registry is None

    def test_audit_log_no_watermark(self):
        log = WatermarkAuditLog.objects.create(
            uploaded_file_name="no_wm.wav",
            uploaded_file_hash="c" * 64,
            watermark_detected=False,
            confidence_score=0.1,
            processing_time_ms=80,
        )
        assert log.extracted_binary is None
        assert log.matched_registry is None
