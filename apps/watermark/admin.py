"""Django admin registrations."""
from django.contrib import admin
from django.utils.html import format_html

from .models import WatermarkAuditLog, WatermarkRegistry


@admin.register(WatermarkRegistry)
class WatermarkRegistryAdmin(admin.ModelAdmin):
    list_display = [
        "watermark_hex",
        "watermark_binary",
        "watermark_integer",
        "copyright_name",
        "company_name",
        "owner_name",
        "contact_email",
        "created_at",
    ]
    list_filter = ["created_at"]
    search_fields = [
        "watermark_binary",
        "watermark_hex",
        "copyright_name",
        "company_name",
        "owner_name",
        "contact_email",
    ]
    readonly_fields = ["id", "watermark_hex", "created_at", "updated_at"]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"
    fieldsets = [
        (
            "Watermark Identifiers",
            {"fields": ["id", "watermark_binary", "watermark_integer", "watermark_hex"]},
        ),
        (
            "Copyright Owner",
            {"fields": ["copyright_name", "company_name", "owner_name", "contact_email"]},
        ),
        ("Notes", {"fields": ["notes"]}),
        ("Timestamps", {"fields": ["created_at", "updated_at"]}),
    ]

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser


@admin.register(WatermarkAuditLog)
class WatermarkAuditLogAdmin(admin.ModelAdmin):
    list_display = [
        "id",
        "uploaded_file_name",
        "watermark_detected",
        "confidence_display",
        "extracted_binary",
        "registry_link",
        "processing_time_ms",
        "created_at",
    ]
    list_filter = ["watermark_detected", "created_at"]
    search_fields = ["uploaded_file_name", "uploaded_file_hash", "extracted_binary"]
    readonly_fields = [
        "id",
        "uploaded_file_name",
        "uploaded_file_hash",
        "watermark_detected",
        "confidence_score",
        "extracted_binary",
        "extracted_integer",
        "matched_registry",
        "processing_time_ms",
        "created_at",
    ]
    ordering = ["-created_at"]
    date_hierarchy = "created_at"

    @admin.display(description="Confidence")
    def confidence_display(self, obj: WatermarkAuditLog) -> str:
        pct = obj.confidence_score * 100
        colour = "green" if obj.confidence_score >= 0.9 else "orange" if obj.confidence_score >= 0.5 else "red"
        return format_html('<span style="color:{}">{:.1f}%</span>', colour, pct)

    @admin.display(description="Registry Match")
    def registry_link(self, obj: WatermarkAuditLog) -> str:
        if obj.matched_registry:
            return format_html(
                '<a href="/admin/watermark/watermarkregistry/{}/change/">{}</a>',
                obj.matched_registry.pk,
                str(obj.matched_registry),
            )
        return "—"

    def has_add_permission(self, request) -> bool:
        return False

    def has_change_permission(self, request, obj=None) -> bool:
        return False

    def has_delete_permission(self, request, obj=None) -> bool:
        return request.user.is_superuser
