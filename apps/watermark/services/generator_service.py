"""Thread-safe singleton AudioSeal generator (watermark embedder) service."""
import threading

import structlog
import torch
from django.conf import settings

from core.exceptions import WatermarkEmbedError

logger = structlog.get_logger(__name__)

TARGET_SAMPLE_RATE = 16000
NBITS = 16


class AudioSealGeneratorService:
    """
    Wraps the AudioSeal watermark generator with thread-safe lazy initialization.

    Mirrors AudioSealDetectorService: the model is loaded once per process on
    first call and reused across requests, with double-checked locking.
    """

    _generator = None
    _lock = threading.Lock()

    @classmethod
    def get_instance(cls):
        """Return the cached generator, loading it on first call."""
        if cls._generator is None:
            with cls._lock:
                if cls._generator is None:
                    cls._load_generator()
        return cls._generator

    @classmethod
    def _load_generator(cls) -> None:
        from audioseal import AudioSeal

        device = getattr(settings, "AUDIOSEAL_DEVICE", "cpu")
        model_card = getattr(
            settings, "AUDIOSEAL_GENERATOR_MODEL_CARD", "audioseal_wm_16bits"
        )
        logger.info("audioseal_generator_loading", model_card=model_card, device=device)
        generator = AudioSeal.load_generator(model_card, device=device)
        generator.eval()
        cls._generator = generator
        logger.info("audioseal_generator_ready")

    @staticmethod
    def _message_tensor(integer_value: int) -> torch.Tensor:
        """
        Encode a 0–65535 integer as a (1, 16) tensor of 0/1 bits, MSB first.

        Bit order matches DecoderService, which reads bits left-to-right and
        does int(binary, 2) — so a value embedded here decodes back identically.
        """
        binary = format(integer_value, f"0{NBITS}b")
        bits = [int(c) for c in binary]
        return torch.tensor([bits], dtype=torch.int32)

    def embed(
        self,
        audio_tensor: torch.Tensor,
        integer_value: int,
        alpha: float = 1.0,
    ) -> torch.Tensor:
        """
        Embed a 16-bit watermark into a pre-processed audio tensor.

        Args:
            audio_tensor: shape (1, 1, samples) at 16kHz, float32
            integer_value: 0–65535, encoded as 16 bits (MSB first)
            alpha: watermark strength multiplier (1.0 = standard)

        Returns:
            watermarked audio tensor, shape (1, 1, samples), float32
        """
        try:
            generator = self.get_instance()
            message = self._message_tensor(integer_value)
            with torch.no_grad():
                watermarked = generator(
                    audio_tensor,
                    sample_rate=TARGET_SAMPLE_RATE,
                    message=message,
                    alpha=alpha,
                )
        except Exception as exc:
            raise WatermarkEmbedError(f"AudioSeal generator failed: {exc}") from exc

        logger.info(
            "watermark_embed_complete",
            integer=integer_value,
            alpha=alpha,
            samples=watermarked.shape[-1],
        )
        return watermarked
