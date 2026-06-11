"""Repository tests — require database."""
import pytest

from apps.watermark.models import WatermarkRegistry
from apps.watermark.repositories.watermark_repository import (
    WatermarkAuditLogRepository,
    WatermarkRegistryRepository,
)


@pytest.mark.django_db
class TestWatermarkRegistryRepository:
    def setup_method(self):
        self.repo = WatermarkRegistryRepository()

    def _create_entry(self, binary="1010011110101011", integer=42923):
        return self.repo.create(
            watermark_binary=binary,
            watermark_integer=integer,
            copyright_name="TVD",
            owner_name="Alice",
            contact_email="alice@tvd.com",
        )

    def test_create_returns_instance(self):
        entry = self._create_entry()
        assert entry.pk is not None
        assert entry.watermark_integer == 42923

    def test_find_by_integer_returns_entry(self):
        self._create_entry()
        result = self.repo.find_by_integer(42923)
        assert result is not None
        assert result.watermark_integer == 42923

    def test_find_by_integer_returns_none_when_missing(self):
        assert self.repo.find_by_integer(99999) is None

    def test_find_by_binary_returns_entry(self):
        self._create_entry()
        result = self.repo.find_by_binary("1010011110101011")
        assert result is not None

    def test_exists_binary_true_when_present(self):
        self._create_entry()
        assert self.repo.exists_binary("1010011110101011") is True

    def test_exists_binary_false_when_absent(self):
        assert self.repo.exists_binary("0000000000000000") is False

    def test_get_all_returns_queryset(self):
        self._create_entry()
        qs = self.repo.get_all()
        assert qs.count() >= 1

    def test_get_by_id_returns_entry(self):
        entry = self._create_entry()
        result = self.repo.get_by_id(entry.pk)
        assert result == entry

    def test_get_by_id_returns_none_for_missing(self):
        import uuid
        assert self.repo.get_by_id(uuid.uuid4()) is None


@pytest.mark.django_db
class TestWatermarkAuditLogRepository:
    def setup_method(self):
        self.repo = WatermarkAuditLogRepository()

    def test_create_audit_log(self):
        log = self.repo.create(
            uploaded_file_name="test.wav",
            uploaded_file_hash="a" * 64,
            watermark_detected=False,
            confidence_score=0.1,
            processing_time_ms=50,
        )
        assert log.pk is not None

    def test_filter_by_hash(self):
        self.repo.create(
            uploaded_file_name="f.wav",
            uploaded_file_hash="b" * 64,
            watermark_detected=False,
            confidence_score=0.2,
            processing_time_ms=30,
        )
        qs = self.repo.filter_by_hash("b" * 64)
        assert qs.count() == 1

    def test_get_all_returns_queryset(self):
        self.repo.create(
            uploaded_file_name="g.wav",
            uploaded_file_hash="c" * 64,
            watermark_detected=False,
            confidence_score=0.3,
            processing_time_ms=20,
        )
        assert self.repo.get_all().count() >= 1
