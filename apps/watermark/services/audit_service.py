"""Audit trail service — creates immutable verification records."""
import hashlib
from typing import Optional

import structlog

from apps.watermark.domain.entities import WatermarkPayload
from apps.watermark.models import WatermarkAuditLog, WatermarkRegistry
from apps.watermark.repositories.watermark_repository import WatermarkAuditLogRepository

logger = structlog.get_logger(__name__)


class AuditService:
    def __init__(self, repository: WatermarkAuditLogRepository) -> None:
        self._repo = repository

    def record(
        self,
        *,
        file_name: str,
        file_bytes: bytes,
        payload: Optional[WatermarkPayload],
        registry_match: Optional[WatermarkRegistry],
        processing_ms: int,
        confidence_score: float,
    ) -> WatermarkAuditLog:
        """
        Create an immutable audit log entry for a verification attempt.

        Args:
            file_name:       Original filename from the upload
            file_bytes:      Raw file bytes — SHA-256 computed here, never stored
            payload:         Decoded watermark payload, or None if not detected
            registry_match:  Matched registry entry, or None
            processing_ms:   Wall-clock processing time
            confidence_score: Raw confidence from the detector
        """
        sha256 = hashlib.sha256(file_bytes).hexdigest()

        log = self._repo.create(
            uploaded_file_name=file_name,
            uploaded_file_hash=sha256,
            watermark_detected=payload is not None,
            confidence_score=confidence_score,
            extracted_binary=payload.binary if payload else None,
            extracted_integer=payload.integer if payload else None,
            matched_registry=registry_match,
            processing_time_ms=processing_ms,
        )

        logger.info(
            "audit_log_created",
            audit_id=str(log.id),
            file_name=file_name,
            sha256_prefix=sha256[:8],
            detected=payload is not None,
            confidence=round(confidence_score, 4),
            processing_ms=processing_ms,
        )
        return log
