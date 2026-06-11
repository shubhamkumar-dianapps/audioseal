"""Data Transfer Objects for cross-layer communication."""
from dataclasses import dataclass, field
from typing import Optional
from uuid import UUID


@dataclass
class RegistryCreateDTO:
    watermark_binary: str
    copyright_name: str
    company_name: str
    owner_name: str
    contact_email: str
    notes: str = ""


@dataclass
class VerificationResult:
    watermark_detected: bool
    confidence_score: float
    extracted_binary: Optional[str]
    extracted_integer: Optional[int]
    extracted_hex: Optional[str]
    ownership_verified: bool
    copyright_name: Optional[str] = None
    company_name: Optional[str] = None
    owner_name: Optional[str] = None
    contact_email: Optional[str] = None
    matched_registry_id: Optional[UUID] = None
    processing_time_ms: int = 0
    audit_log_id: Optional[UUID] = None
