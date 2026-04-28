"""
merchants/serializers.py
========================
MerchantSerializer      — full profile + live balance breakdown
LedgerEntrySerializer   — single ledger row
MerchantListSerializer  — lightweight id + name for the dev merchant switcher
"""

from rest_framework import serializers

from .models import LedgerEntry, Merchant


class LedgerEntrySerializer(serializers.ModelSerializer):
    """Read-only serializer for a single ledger row."""

    class Meta:
        model = LedgerEntry
        fields = [
            "id",
            "entry_type",
            "amount_paise",
            "reference_id",
            "description",
            "created_at",
        ]
        read_only_fields = fields


class MerchantSerializer(serializers.ModelSerializer):
    """
    Full merchant profile with a live balance breakdown.

    `balance` is a SerializerMethodField that calls get_balance_breakdown()
    which runs DB aggregation.  Do NOT call this inside a tight loop — it
    issues three SQL queries per merchant.
    """

    balance = serializers.SerializerMethodField()

    class Meta:
        model = Merchant
        fields = ["id", "name", "email", "bank_account_id", "balance"]
        read_only_fields = fields

    def get_balance(self, obj: Merchant) -> dict:
        return obj.get_balance_breakdown()


class MerchantListSerializer(serializers.ModelSerializer):
    """
    Lightweight serializer for the dev-only merchant switcher.
    Exposes only id and name — never exposes email or bank details.
    """

    class Meta:
        model = Merchant
        fields = ["id", "name"]
        read_only_fields = fields
