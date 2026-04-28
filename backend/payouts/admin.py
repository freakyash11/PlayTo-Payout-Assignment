from django.contrib import admin

from .models import IdempotencyRecord, Payout


@admin.register(Payout)
class PayoutAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "merchant",
        "amount_paise",
        "status",
        "attempts",
        "created_at",
        "updated_at",
    )
    list_filter = ("status",)
    search_fields = ("merchant__name", "idempotency_key")
    readonly_fields = ("id", "created_at", "updated_at")


@admin.register(IdempotencyRecord)
class IdempotencyRecordAdmin(admin.ModelAdmin):
    list_display = ("idempotency_key", "merchant", "created_at")
    search_fields = ("idempotency_key", "merchant__name")
    readonly_fields = ("id", "created_at")
