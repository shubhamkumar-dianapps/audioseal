"""Business logic for watermark registration and ownership lookup."""
from typing import Optional

import structlog

from apps.watermark.domain.dto import RegistryCreateDTO
from apps.watermark.models import WatermarkRegistry
from apps.watermark.repositories.watermark_repository import WatermarkRegistryRepository
from core.exceptions import InvalidWatermarkBinaryError, WatermarkAlreadyExistsError, WatermarkNotFoundError

logger = structlog.get_logger(__name__)


class RegistryService:
    def __init__(self, repository: WatermarkRegistryRepository) -> None:
        self._repo = repository

    def lookup_by_integer(self, integer_value: int) -> Optional[WatermarkRegistry]:
        """Return registry entry for the given integer, or None if not registered."""
        return self._repo.find_by_integer(integer_value)

    def get_or_404(self, integer_value: int) -> WatermarkRegistry:
        """Return registry entry or raise WatermarkNotFoundError."""
        entry = self._repo.find_by_integer(integer_value)
        if entry is None:
            raise WatermarkNotFoundError(
                f"No watermark registered with integer value {integer_value}"
            )
        return entry

    def register(self, dto: RegistryCreateDTO) -> WatermarkRegistry:
        """
        Register a new copyright ownership watermark.

        Validates binary format, checks uniqueness, auto-computes integer + hex.

        Raises:
            InvalidWatermarkBinaryError if binary is not exactly 16 chars of 0/1
            WatermarkAlreadyExistsError if binary is already registered
        """
        if len(dto.watermark_binary) != 16 or not all(c in "01" for c in dto.watermark_binary):
            raise InvalidWatermarkBinaryError(
                "watermark_binary must be exactly 16 characters containing only '0' and '1'"
            )

        if self._repo.exists_binary(dto.watermark_binary):
            raise WatermarkAlreadyExistsError(
                f"Watermark '{dto.watermark_binary}' is already registered"
            )

        integer_value = int(dto.watermark_binary, 2)
        hex_value = format(integer_value, "04X")

        entry = self._repo.create(
            watermark_binary=dto.watermark_binary,
            watermark_integer=integer_value,
            watermark_hex=hex_value,
            copyright_name=dto.copyright_name,
            company_name=dto.company_name,
            owner_name=dto.owner_name,
            contact_email=dto.contact_email,
            notes=dto.notes,
        )

        logger.info(
            "watermark_registered",
            binary=dto.watermark_binary,
            integer=integer_value,
            owner=dto.owner_name,
        )
        return entry
