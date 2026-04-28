"""
management/commands/verify_ledger_integrity.py
===============================================
Usage:
    python manage.py verify_ledger_integrity

Verifies the invariant: sum(CREDIT entries) - sum(DEBIT entries) = available_balance.

For each merchant:
  1. Sums all CREDIT and DEBIT LedgerEntry amounts
  2. Computes net_balance = credits - debits
  3. Sums amount_paise for all Payouts in status IN ('pending', 'processing')
  4. Computes available = net_balance - held
  5. Verifies every Payout has a matching DEBIT LedgerEntry

Prints a summary per merchant and any warnings.
"""

from django.core.management.base import BaseCommand
from django.db.models import Q, Sum

from merchants.models import LedgerEntry, Merchant
from payouts.models import Payout


def _paise_to_inr(paise: int) -> str:
    """Format paise as a human-readable ₹ amount."""
    return f"₹{paise / 100:,.2f}"


class Command(BaseCommand):
    help = "Verify ledger integrity for all merchants."

    def handle(self, *args, **options):
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n📊 Verifying ledger integrity…\n")
        )

        merchants = Merchant.objects.all().order_by("created_at")

        if not merchants.exists():
            self.stdout.write(self.style.WARNING("No merchants found."))
            return

        total_warnings = 0

        for merchant in merchants:
            # 1. Compute total_credits
            total_credits = (
                merchant.ledger_entries.filter(entry_type="CREDIT").aggregate(
                    total=Sum("amount_paise")
                )["total"]
                or 0
            )

            # 2. Compute total_debits
            total_debits = (
                merchant.ledger_entries.filter(entry_type="DEBIT").aggregate(
                    total=Sum("amount_paise")
                )["total"]
                or 0
            )

            # 3. Compute net_balance
            net_balance = total_credits - total_debits

            # 4. Compute held (sum of pending + processing payouts)
            held = (
                Payout.objects.filter(
                    merchant=merchant,
                    status__in=["pending", "processing"],
                ).aggregate(total=Sum("amount_paise"))["total"]
                or 0
            )

            # 5. Compute available
            available = net_balance - held

            # 6. Check: every Payout must have a matching DEBIT LedgerEntry
            payouts = Payout.objects.filter(merchant=merchant).only("id")
            merchant_warnings = 0
            for payout in payouts:
                debit_entry = merchant.ledger_entries.filter(
                    entry_type="DEBIT",
                    reference_id=str(payout.id),
                ).exists()
                if not debit_entry:
                    self.stdout.write(
                        self.style.WARNING(
                            f"  ⚠️  WARNING: Payout {payout.id} has no matching DEBIT entry"
                        )
                    )
                    merchant_warnings += 1

            # 7. Print summary line
            status = "✓" if merchant_warnings == 0 else f"⚠️  ({merchant_warnings} issues)"
            self.stdout.write(
                f"  Merchant {merchant.name}: "
                f"net={_paise_to_inr(net_balance)}, "
                f"held={_paise_to_inr(held)}, "
                f"available={_paise_to_inr(available)} {status}"
            )

            total_warnings += merchant_warnings

        self.stdout.write("")
        if total_warnings == 0:
            self.stdout.write(self.style.SUCCESS("✓ All merchants have valid ledgers."))
        else:
            self.stdout.write(
                self.style.ERROR(f"✗ Found {total_warnings} ledger issue(s).")
            )
