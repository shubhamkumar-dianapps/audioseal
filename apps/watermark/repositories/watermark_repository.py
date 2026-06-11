"""Repository layer — isolates all ORM access from business logic."""
from typing import Optional
from uuid import UUID

from django.db.models import QuerySet

from apps.watermark.models import WatermarkAuditLog, WatermarkRegistry


class WatermarkRegistryRepository:
    def find_by_integer(self, value: int) -> Optional[WatermarkRegistry]:
        return WatermarkRegistry.objects.filter(watermark_integer=value).first()

    def find_by_binary(self, binary: str) -> Optional[WatermarkRegistry]:
        return WatermarkRegistry.objects.filter(watermark_binary=binary).first()

    def exists_binary(self, binary: str) -> bool:
        return WatermarkRegistry.objects.filter(watermark_binary=binary).exists()

    def create(self, **kwargs) -> WatermarkRegistry:
        return WatermarkRegistry.objects.create(**kwargs)

    def get_all(self) -> QuerySet:
        return WatermarkRegistry.objects.all()

    def get_by_id(self, pk: UUID) -> Optional[WatermarkRegistry]:
        return WatermarkRegistry.objects.filter(pk=pk).first()


class WatermarkAuditLogRepository:
    def create(self, **kwargs) -> WatermarkAuditLog:
        return WatermarkAuditLog.objects.create(**kwargs)

    def get_all(self) -> QuerySet:
        return WatermarkAuditLog.objects.all()

    def get_by_id(self, pk: UUID) -> Optional[WatermarkAuditLog]:
        return WatermarkAuditLog.objects.filter(pk=pk).first()

    def filter_by_hash(self, sha256: str) -> QuerySet:
        return WatermarkAuditLog.objects.filter(uploaded_file_hash=sha256)
