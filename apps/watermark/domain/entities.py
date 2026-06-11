"""Pure domain value objects — no Django ORM dependency."""
from dataclasses import dataclass


@dataclass(frozen=True)
class WatermarkPayload:
    """Decoded watermark extracted from an audio file."""

    binary: str       # e.g. "1010011110101011"
    integer: int      # e.g. 42923
    hex_value: str    # e.g. "A7AB"
    confidence: float # 0.0 – 1.0


@dataclass(frozen=True)
class AudioFileInfo:
    """Metadata about a submitted audio file."""

    original_name: str
    sha256_hash: str
    sample_rate: int
    duration_seconds: float
