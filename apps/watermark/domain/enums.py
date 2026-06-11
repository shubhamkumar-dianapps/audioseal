"""Domain enumerations."""
from django.db import models


class DetectionStatus(models.TextChoices):
    DETECTED = "detected", "Watermark Detected"
    NOT_DETECTED = "not_detected", "No Watermark Found"
    ERROR = "error", "Processing Error"
