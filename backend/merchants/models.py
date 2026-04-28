import uuid

from django.db import models
from django.db.models import Sum


class Merchant(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    email = models.EmailField(unique=True)
    bank_account_id = models.CharField(max_length=100)  # simulated bank account
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Merchant"
        verbose_name_plural = "Merchants"

    def __str__(self):
        return f"{self.name} <{self.email}>"

    def get_balance_breakdown(self):
        """Returns dict with available_balance and held_balance using DB aggregation.

        NOTE: Importing Payout here (inside the method) avoids a circular import
        since payouts.models imports nothing from merchants.models at module level.
        """
        from django.db.models import Q  # noqa: F401 – kept for future filters
        from payouts.models import Payout

        total_credits = (
            self.ledger_entries.filter(entry_type="CREDIT")
            .aggregate(total=Sum("amount_paise"))["total"]
            or 0
        )

        total_debits = (
            self.ledger_entries.filter(entry_type="DEBIT")
            .aggregate(total=Sum("amount_paise"))["total"]
            or 0
        )

        held = (
            Payout.objects.filter(
                merchant=self,
                status__in=["pending", "processing"],
            )
            .aggregate(total=Sum("amount_paise"))["total"]
            or 0
        )

        net_balance = total_credits - total_debits
        available = net_balance - held

        return {
            "net_balance_paise": net_balance,
            "held_paise": held,
            "available_paise": available,
        }


class LedgerEntry(models.Model):
    ENTRY_TYPE_CHOICES = [
        ("CREDIT", "credit"),
        ("DEBIT", "debit"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        Merchant,
        on_delete=models.PROTECT,
        related_name="ledger_entries",
    )
    entry_type = models.CharField(max_length=6, choices=ENTRY_TYPE_CHOICES)
    # Stored in paise (integer). Never use FloatField or DecimalField for money.
    amount_paise = models.BigIntegerField()
    reference_id = models.CharField(max_length=255)  # links to payout / payment ID
    description = models.CharField(max_length=500, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Ledger Entry"
        verbose_name_plural = "Ledger Entries"
        indexes = [
            models.Index(fields=["merchant", "entry_type"]),
            models.Index(fields=["reference_id"]),
        ]

    def __str__(self):
        return (
            f"{self.entry_type} ₹{self.amount_paise / 100:.2f}"
            f" | {self.merchant.name}"
        )
