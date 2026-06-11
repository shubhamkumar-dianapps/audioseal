"""Pure-computation watermark decoder — no I/O, fully unit-testable."""
from typing import Optional

import structlog
import torch

from apps.watermark.domain.entities import WatermarkPayload

logger = structlog.get_logger(__name__)


class DecoderService:
    """
    Converts raw AudioSeal detector output into a WatermarkPayload value object.

    Stateless — safe to share across requests.
    """

    def decode(
        self,
        confidence: float,
        message: Optional[torch.Tensor],
    ) -> Optional[WatermarkPayload]:
        """
        Args:
            confidence: float from DetectorService.detect()
            message: Tensor (1, 16) with binary 0/1 bits, or None

        Returns:
            WatermarkPayload if message is provided, else None
        """
        if message is None:
            logger.info("watermark_decode_skipped", reason="no_message")
            return None

        # message shape: (1, 16) — already binary (0 or 1 after detect_watermark)
        bits = [int(b) for b in message[0].tolist()]
        binary = "".join(str(b) for b in bits)
        integer = int(binary, 2)
        hex_value = hex(integer)[2:].upper().zfill(4)

        payload = WatermarkPayload(
            binary=binary,
            integer=integer,
            hex_value=hex_value,
            confidence=confidence,
        )
        logger.info(
            "watermark_decoded",
            binary=binary,
            integer=integer,
            hex=hex_value,
            confidence=round(confidence, 4),
        )
        return payload
