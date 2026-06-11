"""ORM models for watermark registry and audit trail."""
import uuid

from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class WatermarkRegistry(models.Model):
    """Maps a unique 16-bit binary watermark to a copyright owner."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    watermark_binary = models.CharField(
        max_length=16,
        unique=True,
        db_index=True,
        help_text="16-character binary string ('0'/'1') extracted by AudioSeal.",
    )
    watermark_integer = models.IntegerField(
        unique=True,
        db_index=True,
        validators=[MinValueValidator(0), MaxValueValidator(65535)],
        help_text="Integer value of the 16-bit watermark (0–65535).",
    )
    watermark_hex = models.CharField(
        max_length=8,
        help_text="Hex representation — derived from watermark_integer on save.",
    )

    copyright_name = models.CharField(max_length=255)
    company_name = models.CharField(max_length=255, blank=True, default="")
    owner_name = models.CharField(max_length=255)
    contact_email = models.EmailField(max_length=254)
    notes = models.TextField(blank=True, default="")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "watermark_registry"
        ordering = ["-created_at"]
        verbose_name = "Watermark Registry Entry"
        verbose_name_plural = "Watermark Registry Entries"
        indexes = [
            models.Index(fields=["watermark_binary"], name="idx_registry_binary"),
            models.Index(fields=["watermark_integer"], name="idx_registry_integer"),
            models.Index(fields=["contact_email"], name="idx_registry_email"),
            models.Index(fields=["created_at"], name="idx_registry_created"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(watermark_integer__gte=0) & models.Q(watermark_integer__lte=65535),
                name="chk_registry_integer_range",
            ),
        ]

    def save(self, *args, **kwargs) -> None:
        self.watermark_hex = format(self.watermark_integer, "04X")
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"[{self.watermark_hex}] {self.copyright_name}"


class WatermarkAuditLog(models.Model):
    """Immutable audit record of every watermark verification attempt."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)

    uploaded_file_name = models.CharField(max_length=500)
    uploaded_file_hash = models.CharField(
        max_length=64, db_index=True, help_text="SHA-256 hex digest of the uploaded file."
    )

    watermark_detected = models.BooleanField(default=False)
    confidence_score = models.FloatField(
        validators=[MinValueValidator(0.0), MaxValueValidator(1.0)],
        help_text="Detector confidence in [0.0, 1.0].",
    )

    extracted_binary = models.CharField(max_length=16, null=True, blank=True, db_index=True)
    extracted_integer = models.IntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(0), MaxValueValidator(65535)],
    )

    matched_registry = models.ForeignKey(
        "WatermarkRegistry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="audit_logs",
        db_index=True,
    )

    processing_time_ms = models.IntegerField(
        validators=[MinValueValidator(0)],
        help_text="Wall-clock time in ms for the full detection pipeline.",
    )

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "watermark_audit_log"
        ordering = ["-created_at"]
        verbose_name = "Watermark Audit Log"
        verbose_name_plural = "Watermark Audit Logs"
        indexes = [
            models.Index(fields=["uploaded_file_hash"], name="idx_audit_file_hash"),
            models.Index(fields=["watermark_detected"], name="idx_audit_detected"),
            models.Index(
                fields=["watermark_detected", "created_at"],
                name="idx_audit_detected_created",
            ),
            models.Index(fields=["extracted_binary"], name="idx_audit_extracted_binary"),
            models.Index(fields=["created_at"], name="idx_audit_created"),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(confidence_score__gte=0.0) & models.Q(confidence_score__lte=1.0),
                name="chk_audit_confidence_range",
            ),
            models.CheckConstraint(
                condition=models.Q(processing_time_ms__gte=0),
                name="chk_audit_processing_positive",
            ),
            # If watermark detected, extracted_binary must be present
            models.CheckConstraint(
                condition=(
                    models.Q(watermark_detected=False)
                    | models.Q(extracted_binary__isnull=False)
                ),
                name="chk_audit_detected_implies_binary",
            ),
        ]

    def __str__(self) -> str:
        status = "detected" if self.watermark_detected else "not detected"
        return f"{self.uploaded_file_name} — {status}"
