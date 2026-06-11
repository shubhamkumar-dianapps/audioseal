"""AppConfig — pre-loads AudioSeal detector on startup."""
from django.apps import AppConfig


class WatermarkConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.watermark"
    verbose_name = "AudioSeal Watermark Service"

    def ready(self) -> None:
        # Pre-load the detector model at startup to avoid cold-start latency
        # on the first API request. The singleton caches the loaded model.
        try:
            from .services.detector_service import AudioSealDetectorService
            from .services.generator_service import AudioSealGeneratorService

            AudioSealDetectorService.get_instance()
            AudioSealGeneratorService.get_instance()
        except Exception:
            # Non-fatal: models will load lazily on first request instead.
            import logging

            logging.getLogger(__name__).warning(
                "AudioSeal models could not be pre-loaded at startup. "
                "They will be loaded on first request."
            )
