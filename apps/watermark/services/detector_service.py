"""Thread-safe singleton AudioSeal detector service."""
import threading
from typing import Optional, Tuple

import structlog
import torch
from django.conf import settings

from core.exceptions import WatermarkDetectionError

logger = structlog.get_logger(__name__)


class AudioSealDetectorService:
    """
    Wraps the AudioSeal watermark detector with thread-safe lazy initialization.

    The model is loaded once per process on first call and reused across all
    subsequent requests. Uses double-checked locking to be safe under concurrency.
    """

    _detector = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Return the cached detector, loading it on first call."""
        if cls._detector is None:
            with cls._lock:
                if cls._detector is None:
                    cls._load_detector()
        return cls._detector

    @classmethod
    def _load_detector(cls) -> None:
        from audioseal import AudioSeal

        device = getattr(settings, "AUDIOSEAL_DEVICE", "cpu")
        model_card = getattr(settings, "AUDIOSEAL_MODEL_CARD", "audioseal_detector_16bits")
        logger.info("audioseal_detector_loading", model_card=model_card, device=device)
        detector = AudioSeal.load_detector(model_card, device=device)
        detector.eval()
        cls._detector = detector
        logger.info("audioseal_detector_ready")

    def detect(self, audio_tensor: torch.Tensor) -> Tuple[float, Optional[torch.Tensor]]:
        """
        Run watermark detection on a pre-processed audio tensor.

        Args:
            audio_tensor: shape (1, 1, samples) at 16kHz

        Returns:
            (confidence, message_tensor_or_None)
            confidence: float [0.0, 1.0]
            message_tensor: Tensor (1, 16) with binary 0/1 bits, or None if below threshold
        """
        threshold: float = getattr(settings, "WATERMARK_DETECTION_THRESHOLD", 0.5)

        try:
            detector = self.get_instance()
            with torch.no_grad():
                detect_prob, message = detector.detect_watermark(
                    audio_tensor,
                    sample_rate=16000,
                    detection_threshold=threshold,
                    message_threshold=0.5,
                )
        except Exception as exc:
            raise WatermarkDetectionError(f"AudioSeal detector failed: {exc}") from exc

        confidence = float(detect_prob[0].item())
        logger.info("watermark_detection_complete", confidence=round(confidence, 4))

        if confidence >= threshold:
            return confidence, message
        return confidence, None
