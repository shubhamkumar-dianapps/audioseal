"""Request and response serializers for the watermark API."""
import os

from rest_framework import serializers

ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}
MAX_FILE_SIZE = 52_428_800  # 50 MB


# ---------------------------------------------------------------------------
# Request serializers
# ---------------------------------------------------------------------------
class VerifyRequestSerializer(serializers.Serializer):
    audio_file = serializers.FileField()

    def validate_audio_file(self, value):
        _, ext = os.path.splitext(value.name)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported extension '{ext}'. Accepted: {sorted(ALLOWED_EXTENSIONS)}"
            )
        if value.size > MAX_FILE_SIZE:
            raise serializers.ValidationError(
                f"File size {value.size / 1_048_576:.1f} MB exceeds 50 MB limit."
            )
        return value


class EmbedRequestSerializer(serializers.Serializer):
    audio_file = serializers.FileField()
    watermark_integer = serializers.IntegerField(min_value=0, max_value=65535)
    alpha = serializers.FloatField(
        min_value=0.0, max_value=2.0, default=1.0, required=False
    )

    def validate_audio_file(self, value):
        _, ext = os.path.splitext(value.name)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            raise serializers.ValidationError(
                f"Unsupported extension '{ext}'. Accepted: {sorted(ALLOWED_EXTENSIONS)}"
            )
        if value.size > MAX_FILE_SIZE:
            raise serializers.ValidationError(
                f"File size {value.size / 1_048_576:.1f} MB exceeds 50 MB limit."
            )
        return value


class RegisterRequestSerializer(serializers.Serializer):
    watermark_binary = serializers.CharField(min_length=16, max_length=16)
    copyright_name = serializers.CharField(max_length=255)
    company_name = serializers.CharField(max_length=255, default="", allow_blank=True)
    owner_name = serializers.CharField(max_length=255)
    contact_email = serializers.EmailField(max_length=254)
    notes = serializers.CharField(default="", allow_blank=True, required=False)

    def validate_watermark_binary(self, value: str) -> str:
        if not all(c in "01" for c in value):
            raise serializers.ValidationError(
                "watermark_binary must contain only '0' and '1' characters."
            )
        return value


# ---------------------------------------------------------------------------
# Response serializers
# ---------------------------------------------------------------------------
class OwnerSerializer(serializers.Serializer):
    copyright_name = serializers.CharField()
    company_name = serializers.CharField()
    owner_name = serializers.CharField()
    contact_email = serializers.EmailField()


class VerificationResponseSerializer(serializers.Serializer):
    watermark_detected = serializers.BooleanField()
    confidence = serializers.FloatField()
    binary_message = serializers.CharField(allow_null=True)
    integer_message = serializers.IntegerField(allow_null=True)
    hex_message = serializers.CharField(allow_null=True)
    ownership_verified = serializers.BooleanField()
    owner = OwnerSerializer(allow_null=True)
    audit_id = serializers.UUIDField()


class RegisterResponseSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    watermark_binary = serializers.CharField()
    watermark_integer = serializers.IntegerField()
    watermark_hex = serializers.CharField()
    copyright_name = serializers.CharField()
    company_name = serializers.CharField()
    owner_name = serializers.CharField()
    contact_email = serializers.EmailField()
    created_at = serializers.DateTimeField()


class LookupResponseSerializer(serializers.Serializer):
    watermark_integer = serializers.IntegerField()
    watermark_binary = serializers.CharField()
    watermark_hex = serializers.CharField()
    owner = OwnerSerializer()
    registered_at = serializers.DateTimeField()


class AuditLogSerializer(serializers.Serializer):
    id = serializers.UUIDField()
    uploaded_file_name = serializers.CharField()
    uploaded_file_hash = serializers.CharField()
    watermark_detected = serializers.BooleanField()
    confidence_score = serializers.FloatField()
    extracted_binary = serializers.CharField(allow_null=True)
    extracted_integer = serializers.IntegerField(allow_null=True)
    processing_time_ms = serializers.IntegerField()
    created_at = serializers.DateTimeField()
