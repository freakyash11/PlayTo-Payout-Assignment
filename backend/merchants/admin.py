from django.contrib import admin

from .models import LedgerEntry, Merchant


@admin.register(Merchant)
class MerchantAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "bank_account_id", "created_at")
    search_fields = ("name", "email")
    readonly_fields = ("id", "created_at")


@admin.register(LedgerEntry)
class LedgerEntryAdmin(admin.ModelAdmin):
    list_display = (
        "merchant",
        "entry_type",
        "amount_paise",
        "reference_id",
        "created_at",
    )
    list_filter = ("entry_type",)
    search_fields = ("merchant__name", "reference_id")
    readonly_fields = ("id", "created_at")
