"""Watermark API URL patterns."""
from django.urls import path

from .views import (
    AuditLogListView,
    EmbedWatermarkView,
    LookupWatermarkView,
    RegisterWatermarkView,
    VerifyWatermarkView,
)

app_name = "watermark"

urlpatterns = [
    path("embed/", EmbedWatermarkView.as_view(), name="embed"),
    path("verify/", VerifyWatermarkView.as_view(), name="verify"),
    path("register/", RegisterWatermarkView.as_view(), name="register"),
    path("lookup/<int:watermark_integer>/", LookupWatermarkView.as_view(), name="lookup"),
    path("audit/", AuditLogListView.as_view(), name="audit-list"),
]
