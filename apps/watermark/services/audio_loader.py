"""Audio loading, validation, and preprocessing service."""
import io
import os
from typing import Tuple

import filetype
import numpy as np
import soundfile as sf
import structlog
import torch
import torchaudio.transforms as T
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile

from core.exceptions import AudioTooLargeError, CorruptedAudioError, UnsupportedAudioFormatError

logger = structlog.get_logger(__name__)

TARGET_SAMPLE_RATE = 16000
ALLOWED_EXTENSIONS = {".wav", ".mp3", ".flac", ".m4a", ".ogg"}
ALLOWED_FILETYPES = {"wav", "mp3", "flac", "m4a", "ogg"}

UploadedFile = InMemoryUploadedFile | TemporaryUploadedFile


def tensor_to_wav_bytes(
    audio_tensor: torch.Tensor, sample_rate: int = TARGET_SAMPLE_RATE
) -> bytes:
    """
    Encode a float32 audio tensor to in-memory WAV bytes (16-bit PCM).

    Accepts shape (1, 1, samples) (generator/detector layout) or (1, samples).
    No temp files — everything goes through BytesIO.
    """
    waveform = audio_tensor.detach().cpu()
    if waveform.dim() == 3:
        waveform = waveform[0]  # (1, 1, samples) -> (1, samples)
    # soundfile expects (samples, channels)
    data = waveform.t().numpy()
    buf = io.BytesIO()
    sf.write(buf, data, samplerate=sample_rate, format="WAV", subtype="PCM_16")
    return buf.getvalue()


class AudioLoaderService:
    """
    Accepts a Django uploaded file, validates it, and returns a normalised
    float32 tensor at 16kHz for AudioSeal inference.

    All processing is in-memory via BytesIO — no temp files written to disk.
    """

    def load(self, uploaded_file: UploadedFile) -> Tuple[torch.Tensor, bytes]:
        """
        Returns:
            (audio_tensor, file_bytes)
            audio_tensor: shape (1, 1, samples) at 16kHz, float32, normalised [-1, 1]
            file_bytes: raw bytes for SHA-256 hashing in AuditService

        Raises:
            AudioTooLargeError         if file exceeds size/duration limit
            UnsupportedAudioFormatError if extension or magic bytes are wrong
            CorruptedAudioError        if torchaudio cannot decode the file
        """
        max_bytes: int = getattr(settings, "AUDIOSEAL_MAX_FILE_BYTES", 52_428_800)
        max_duration: int = getattr(settings, "AUDIOSEAL_MAX_DURATION_SEC", 600)

        log = logger.bind(file_name=uploaded_file.name, file_size=uploaded_file.size)
        log.info("audio_load_started")

        # --- 1. Size check (cheapest, first) ---
        if uploaded_file.size > max_bytes:
            raise AudioTooLargeError(
                f"File size {uploaded_file.size / 1_048_576:.1f} MB exceeds "
                f"limit of {max_bytes / 1_048_576:.0f} MB"
            )

        # --- 2. Extension check ---
        _, ext = os.path.splitext(uploaded_file.name)
        if ext.lower() not in ALLOWED_EXTENSIONS:
            raise UnsupportedAudioFormatError(
                f"Extension '{ext}' not supported. Accepted: {sorted(ALLOWED_EXTENSIONS)}"
            )

        # --- 3. Read to memory ---
        uploaded_file.seek(0)
        file_bytes = uploaded_file.read()

        # --- 4. Magic bytes check ---
        kind = filetype.guess(file_bytes)
        if kind is None or kind.extension not in ALLOWED_FILETYPES:
            detected = kind.extension if kind else "unknown"
            raise UnsupportedAudioFormatError(
                f"File content does not match an accepted audio format "
                f"(detected: {detected})"
            )

        # --- 5. Decode audio using soundfile (works without torchcodec) ---
        buf = io.BytesIO(file_bytes)
        try:
            data, sample_rate = sf.read(buf, dtype="float32", always_2d=True)
            # soundfile returns shape (samples, channels) → transpose to (channels, samples)
            waveform = torch.from_numpy(data.T)
        except Exception as exc:
            raise CorruptedAudioError(f"Could not decode audio: {exc}") from exc

        # --- 6. Duration check ---
        duration = waveform.shape[-1] / sample_rate
        if duration > max_duration:
            raise AudioTooLargeError(
                f"Audio duration {duration:.1f}s exceeds limit of {max_duration}s"
            )

        # --- 7. Convert to mono ---
        if waveform.shape[0] > 1:
            waveform = waveform.mean(dim=0, keepdim=True)

        # --- 8. Resample to 16kHz ---
        if sample_rate != TARGET_SAMPLE_RATE:
            resampler = T.Resample(orig_freq=sample_rate, new_freq=TARGET_SAMPLE_RATE)
            waveform = resampler(waveform)

        # --- 9. Normalise to [-1, 1] ---
        peak = waveform.abs().max()
        if peak > 0:
            waveform = waveform / peak

        # --- 10. Add batch dimension: (1, samples) → (1, 1, samples) ---
        audio_tensor = waveform.unsqueeze(0)

        log.info(
            "audio_load_complete",
            samples=audio_tensor.shape[-1],
            duration_s=round(audio_tensor.shape[-1] / TARGET_SAMPLE_RATE, 2),
        )
        return audio_tensor, file_bytes
