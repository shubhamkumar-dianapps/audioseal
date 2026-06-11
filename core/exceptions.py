"""Domain exceptions and DRF exception handler."""
from typing import Any

import structlog
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import exception_handler as drf_default_handler

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Base
# ---------------------------------------------------------------------------
class AudioSealServiceError(Exception):
    http_status: int = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code: str = "INTERNAL_ERROR"

    def __init__(self, message: str, detail: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail or {}


# ---------------------------------------------------------------------------
# Audio loading / validation
# ---------------------------------------------------------------------------
class AudioLoadError(AudioSealServiceError):
    http_status = status.HTTP_422_UNPROCESSABLE_ENTITY
    error_code = "AUDIO_LOAD_ERROR"


class UnsupportedAudioFormatError(AudioLoadError):
    error_code = "UNSUPPORTED_AUDIO_FORMAT"


class AudioTooLargeError(AudioLoadError):
    http_status = status.HTTP_413_REQUEST_ENTITY_TOO_LARGE
    error_code = "AUDIO_TOO_LARGE"


class CorruptedAudioError(AudioLoadError):
    error_code = "CORRUPTED_AUDIO"


# ---------------------------------------------------------------------------
# Watermark detection
# ---------------------------------------------------------------------------
class WatermarkDetectionError(AudioSealServiceError):
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "WATERMARK_DETECTION_ERROR"


# ---------------------------------------------------------------------------
# Watermark embedding
# ---------------------------------------------------------------------------
class WatermarkEmbedError(AudioSealServiceError):
    http_status = status.HTTP_500_INTERNAL_SERVER_ERROR
    error_code = "WATERMARK_EMBED_ERROR"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------
class WatermarkNotFoundError(AudioSealServiceError):
    http_status = status.HTTP_404_NOT_FOUND
    error_code = "WATERMARK_NOT_FOUND"


class WatermarkAlreadyExistsError(AudioSealServiceError):
    http_status = status.HTTP_409_CONFLICT
    error_code = "WATERMARK_ALREADY_EXISTS"


class InvalidWatermarkBinaryError(AudioSealServiceError):
    http_status = status.HTTP_400_BAD_REQUEST
    error_code = "INVALID_WATERMARK_BINARY"


# ---------------------------------------------------------------------------
# DRF exception handler
# ---------------------------------------------------------------------------
def custom_exception_handler(exc: Exception, context: dict[str, Any]) -> Response | None:
    request = context.get("request")
    view = context.get("view")

    log = logger.bind(
        view=type(view).__name__ if view else "unknown",
        method=getattr(request, "method", "?"),
        path=getattr(getattr(request, "_request", request), "path", "?"),
    )

    if isinstance(exc, AudioSealServiceError):
        log.warning(
            "domain_exception",
            error_code=exc.error_code,
            message=exc.message,
        )
        return Response(
            {"error": {"code": exc.error_code, "message": exc.message, "detail": exc.detail}},
            status=exc.http_status,
        )

    response = drf_default_handler(exc, context)

    if response is not None:
        log.info("drf_exception", status_code=response.status_code)
        return Response(
            {
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed.",
                    "detail": response.data,
                }
            },
            status=response.status_code,
        )

    log.exception("unhandled_exception")
    return Response(
        {"error": {"code": "INTERNAL_ERROR", "message": "An unexpected error occurred.", "detail": {}}},
        status=status.HTTP_500_INTERNAL_SERVER_ERROR,
    )
