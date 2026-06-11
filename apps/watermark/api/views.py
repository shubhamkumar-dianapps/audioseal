"""API views — orchestration only, no business logic."""
import os
import time
from typing import Any

import structlog
from django.http import HttpResponse
from rest_framework import parsers, status
from rest_framework.permissions import AllowAny
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.watermark.domain.dto import RegistryCreateDTO
from apps.watermark.repositories.watermark_repository import (
    WatermarkAuditLogRepository,
    WatermarkRegistryRepository,
)
from apps.watermark.services.audio_loader import AudioLoaderService, tensor_to_wav_bytes
from apps.watermark.services.audit_service import AuditService
from apps.watermark.services.decoder_service import DecoderService
from apps.watermark.services.detector_service import AudioSealDetectorService
from apps.watermark.services.generator_service import AudioSealGeneratorService
from apps.watermark.services.registry_service import RegistryService
from core.exceptions import AudioSealServiceError, WatermarkAlreadyExistsError, WatermarkNotFoundError

from .serializers import (
    AuditLogSerializer,
    EmbedRequestSerializer,
    LookupResponseSerializer,
    RegisterRequestSerializer,
    RegisterResponseSerializer,
    VerificationResponseSerializer,
    VerifyRequestSerializer,
)

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Module-level service singletons — instantiated once at import time.
# All services are stateless (DetectorService holds the model via class var).
# ---------------------------------------------------------------------------
_registry_repo = WatermarkRegistryRepository()
_audit_repo = WatermarkAuditLogRepository()
_audio_loader = AudioLoaderService()
_detector = AudioSealDetectorService()
_generator = AudioSealGeneratorService()
_decoder = DecoderService()
_registry_svc = RegistryService(_registry_repo)
_audit_svc = AuditService(_audit_repo)


class EmbedWatermarkView(APIView):
    """
    POST /api/watermark/embed/

    Accepts a multipart audio file plus a 16-bit ``watermark_integer`` (0–65535),
    embeds the AudioSeal watermark, and returns the watermarked audio as a
    downloadable WAV file (16kHz mono, 16-bit PCM).

    The decoded value, binary, and hex are returned in response headers:
        X-Watermark-Integer, X-Watermark-Binary, X-Watermark-Hex
    """

    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    permission_classes = [AllowAny]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> HttpResponse:
        serializer = EmbedRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data["audio_file"]
        watermark_integer = serializer.validated_data["watermark_integer"]
        alpha = serializer.validated_data.get("alpha", 1.0)

        log = logger.bind(file_name=uploaded_file.name, watermark_integer=watermark_integer)
        log.info("embed_request_received")

        try:
            audio_tensor, _ = _audio_loader.load(uploaded_file)
            watermarked = _generator.embed(audio_tensor, watermark_integer, alpha)
            wav_bytes = tensor_to_wav_bytes(watermarked)

            binary = format(watermark_integer, "016b")
            hex_value = format(watermark_integer, "04X")
            base, _ = os.path.splitext(uploaded_file.name)
            out_name = f"{base}_watermarked_{watermark_integer}.wav"

            response = HttpResponse(wav_bytes, content_type="audio/wav")
            response["Content-Disposition"] = f'attachment; filename="{out_name}"'
            response["X-Watermark-Integer"] = str(watermark_integer)
            response["X-Watermark-Binary"] = binary
            response["X-Watermark-Hex"] = hex_value
            response["Access-Control-Expose-Headers"] = (
                "X-Watermark-Integer, X-Watermark-Binary, X-Watermark-Hex, Content-Disposition"
            )

            log.info("embed_request_complete", out_name=out_name, alpha=alpha)
            return response

        except AudioSealServiceError:
            raise  # Handled by core.exceptions.custom_exception_handler
        except Exception as exc:
            log.exception("embed_unexpected_error", error=str(exc))
            raise


class VerifyWatermarkView(APIView):
    """
    POST /api/watermark/verify/

    Accepts a multipart audio file, runs AudioSeal detection, looks up
    copyright ownership, records an audit log, and returns the result.
    """

    parser_classes = [parsers.MultiPartParser, parsers.FormParser]
    permission_classes = [AllowAny]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        t0 = time.monotonic()

        serializer = VerifyRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        uploaded_file = serializer.validated_data["audio_file"]
        log = logger.bind(file_name=uploaded_file.name)
        log.info("verify_request_received")

        try:
            audio_tensor, file_bytes = _audio_loader.load(uploaded_file)
            confidence, message = _detector.detect(audio_tensor)
            payload = _decoder.decode(confidence, message)

            registry_match = None
            if payload is not None:
                registry_match = _registry_svc.lookup_by_integer(payload.integer)

            processing_ms = int((time.monotonic() - t0) * 1000)
            audit_log = _audit_svc.record(
                file_name=uploaded_file.name,
                file_bytes=file_bytes,
                payload=payload,
                registry_match=registry_match,
                processing_ms=processing_ms,
                confidence_score=confidence,
            )

            owner_data: dict | None = None
            if registry_match:
                owner_data = {
                    "copyright_name": registry_match.copyright_name,
                    "company_name": registry_match.company_name,
                    "owner_name": registry_match.owner_name,
                    "contact_email": registry_match.contact_email,
                }

            response_data = {
                "watermark_detected": payload is not None,
                "confidence": confidence,
                "binary_message": payload.binary if payload else None,
                "integer_message": payload.integer if payload else None,
                "hex_message": payload.hex_value if payload else None,
                "ownership_verified": registry_match is not None,
                "owner": owner_data,
                "audit_id": audit_log.id,
            }

            log.info(
                "verify_request_complete",
                detected=payload is not None,
                ownership_verified=registry_match is not None,
                processing_ms=processing_ms,
            )
            return Response(
                VerificationResponseSerializer(response_data).data,
                status=status.HTTP_200_OK,
            )

        except AudioSealServiceError:
            raise  # Handled by core.exceptions.custom_exception_handler
        except Exception as exc:
            log.exception("verify_unexpected_error", error=str(exc))
            raise


class RegisterWatermarkView(APIView):
    """
    POST /api/watermark/register/

    Register a new 16-bit binary watermark and associate it with a copyright owner.
    """

    permission_classes = [AllowAny]

    def post(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        serializer = RegisterRequestSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        dto = RegistryCreateDTO(**serializer.validated_data)
        entry = _registry_svc.register(dto)  # raises on error → caught by handler

        response_data = {
            "id": entry.id,
            "watermark_binary": entry.watermark_binary,
            "watermark_integer": entry.watermark_integer,
            "watermark_hex": entry.watermark_hex,
            "copyright_name": entry.copyright_name,
            "company_name": entry.company_name,
            "owner_name": entry.owner_name,
            "contact_email": entry.contact_email,
            "created_at": entry.created_at,
        }
        return Response(
            RegisterResponseSerializer(response_data).data,
            status=status.HTTP_201_CREATED,
        )


class LookupWatermarkView(APIView):
    """
    GET /api/watermark/lookup/<watermark_integer>/

    Retrieve copyright ownership details for a registered watermark.
    """

    permission_classes = [AllowAny]

    def get(self, request: Request, watermark_integer: int, *args: Any, **kwargs: Any) -> Response:
        entry = _registry_svc.get_or_404(watermark_integer)

        response_data = {
            "watermark_integer": entry.watermark_integer,
            "watermark_binary": entry.watermark_binary,
            "watermark_hex": entry.watermark_hex,
            "owner": {
                "copyright_name": entry.copyright_name,
                "company_name": entry.company_name,
                "owner_name": entry.owner_name,
                "contact_email": entry.contact_email,
            },
            "registered_at": entry.created_at,
        }
        return Response(
            LookupResponseSerializer(response_data).data,
            status=status.HTTP_200_OK,
        )


class AuditLogListView(APIView):
    """GET /api/watermark/audit/ — paginated audit log listing."""

    permission_classes = [AllowAny]

    def get(self, request: Request, *args: Any, **kwargs: Any) -> Response:
        logs = _audit_repo.get_all()[:50]
        data = [
            {
                "id": log.id,
                "uploaded_file_name": log.uploaded_file_name,
                "uploaded_file_hash": log.uploaded_file_hash,
                "watermark_detected": log.watermark_detected,
                "confidence_score": log.confidence_score,
                "extracted_binary": log.extracted_binary,
                "extracted_integer": log.extracted_integer,
                "processing_time_ms": log.processing_time_ms,
                "created_at": log.created_at,
            }
            for log in logs
        ]
        return Response(AuditLogSerializer(data, many=True).data)
