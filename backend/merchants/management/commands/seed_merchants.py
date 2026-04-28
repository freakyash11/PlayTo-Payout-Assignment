"""
management/commands/seed_merchants.py
======================================
Usage:
    python manage.py seed_merchants

Creates 3 realistic merchants and seeds each with 5-10 random CREDIT
LedgerEntries (amounts between 10 000 and 500 000 paise).
Prints a balance summary per merchant after seeding.
"""
import random
import uuid

from django.core.management.base import BaseCommand
from django.db import transaction

from merchants.models import LedgerEntry, Merchant

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------
MERCHANT_FIXTURES = [
    {
        "name": "Zephyr Electronics Pvt. Ltd.",
        "email": "payouts@zephyrelectronics.in",
        "bank_account_id": "HDFC00012345678",
    },
    {
        "name": "Mango Street Foods",
        "email": "finance@mangostreetfoods.com",
        "bank_account_id": "ICICI00098765432",
    },
    {
        "name": "BluePine Logistics",
        "email": "accounts@bluepinelogistics.co.in",
        "bank_account_id": "AXIS00056781234",
    },
]

CREDIT_DESCRIPTIONS = [
    "Customer payment received",
    "Marketplace settlement",
    "Refund reversal credit",
    "Monthly subscription credit",
    "Platform bonus credit",
    "Partner payout received",
    "B2B invoice cleared",
    "Cash-on-delivery reconciliation",
    "Dispute won – funds released",
    "Promotional cashback credit",
]


def _paise_to_inr(paise: int) -> str:
    """Format paise as a human-readable ₹ amount."""
    return f"₹{paise / 100:,.2f}"


class Command(BaseCommand):
    help = "Seeds 3 merchants with random CREDIT ledger entries."

    def add_arguments(self, parser):
        parser.add_argument(
            "--reset",
            action="store_true",
            help="Delete existing seed merchants before re-seeding.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        if options["reset"]:
            emails = [m["email"] for m in MERCHANT_FIXTURES]
            deleted, _ = Merchant.objects.filter(email__in=emails).delete()
            self.stdout.write(
                self.style.WARNING(f"  Deleted {deleted} existing merchant record(s).")
            )

        self.stdout.write(self.style.MIGRATE_HEADING("\n🌱  Seeding merchants…\n"))

        for fixture in MERCHANT_FIXTURES:
            merchant, created = Merchant.objects.get_or_create(
                email=fixture["email"],
                defaults={
                    "name": fixture["name"],
                    "bank_account_id": fixture["bank_account_id"],
                },
            )

            action = "Created" if created else "Found existing"
            self.stdout.write(f"  {action}: {merchant}")

            # Generate 5–10 CREDIT entries
            num_entries = random.randint(5, 10)
            entries = []
            for _ in range(num_entries):
                entries.append(
                    LedgerEntry(
                        merchant=merchant,
                        entry_type="CREDIT",
                        amount_paise=random.randint(10_000, 500_000),
                        reference_id=f"PAY-{uuid.uuid4().hex[:10].upper()}",
                        description=random.choice(CREDIT_DESCRIPTIONS),
                    )
                )

            LedgerEntry.objects.bulk_create(entries)
            self.stdout.write(
                f"    → Inserted {num_entries} CREDIT ledger entries."
            )

            # Balance summary (no Payout rows yet, so held will be 0)
            breakdown = merchant.get_balance_breakdown()
            self.stdout.write(
                self.style.SUCCESS(
                    f"    Balance summary:\n"
                    f"      Net balance : {_paise_to_inr(breakdown['net_balance_paise'])}\n"
                    f"      Held        : {_paise_to_inr(breakdown['held_paise'])}\n"
                    f"      Available   : {_paise_to_inr(breakdown['available_paise'])}\n"
                )
            )

        self.stdout.write(self.style.SUCCESS("✅  Done seeding merchants.\n"))
