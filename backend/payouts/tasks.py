"""
payouts/tasks.py
================
Three Celery tasks that drive the payout lifecycle:

  process_pending_payouts  — periodic, every 10 s
  process_single_payout    — dispatched per payout
  retry_stuck_payouts      — periodic, every 30 s

All DB writes that must be atomic (status change + ledger entry) are
wrapped in their own transaction.atomic() block so that a failure in
either operation rolls back both.
"""

import logging
import random
from datetime import timedelta

from celery import shared_task
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


# ────────────────────────────────────────────────────────────────────────────
# Task 1: process_pending_payouts
# ────────────────────────────────────────────────────────────────────────────

@shared_task(name="payouts.tasks.process_pending_payouts")
def process_pending_payouts():
    """
    Periodic task (every 10 s).

    Fetches the ID of every PENDING payout and fans out a
    process_single_payout task for each one.  Uses .only('id')
    so Django does not hydrate full model objects from the DB.
    """
    from .models import Payout  # local import avoids circular-import at module load

    pending = Payout.objects.filter(status=Payout.PENDING).only("id")
    dispatched = 0
    for payout in pending:
        process_single_payout.delay(str(payout.id))
        dispatched += 1

    logger.info("process_pending_payouts: dispatched %d task(s)", dispatched)
    return f"Dispatched {dispatched} payout(s)"


# ────────────────────────────────────────────────────────────────────────────
# Task 2: process_single_payout
# ────────────────────────────────────────────────────────────────────────────

@shared_task(name="payouts.tasks.process_single_payout")
def process_single_payout(payout_id: str):
    """
    Process one payout through the simulated bank settlement flow.

    Transaction 1 — Claim the payout (pending → processing).
      Uses SELECT FOR UPDATE so two workers cannot race on the same row.

    After commit of Tx1, simulate the bank call.

    Transaction 2 — Record the outcome atomically:
      • success  → transition to 'completed'  (no ledger change; debit already posted)
      • failure  → transition to 'failed' + CREDIT reversal entry (both or neither)
      • hung     → do nothing; retry_stuck_payouts will reset it
    """
    from .models import Payout
    from merchants.models import LedgerEntry

    # ── Tx1: claim the payout ──────────────────────────────────────────── #
    with transaction.atomic():
        try:
            payout = Payout.objects.select_for_update().get(id=payout_id)
        except Payout.DoesNotExist:
            logger.error("process_single_payout: payout %s not found", payout_id)
            return f"Payout {payout_id} not found"

        # Guard: another worker may have already picked this up.
        if payout.status != Payout.PENDING:
            logger.info(
                "process_single_payout: skipping %s, status=%s",
                payout_id,
                payout.status,
            )
            return f"Skipped {payout_id}: already {payout.status}"

        payout.transition_to(Payout.PROCESSING)   # raises ValueError if illegal
        payout.processing_started_at = timezone.now()
        payout.attempts += 1
        payout.save()
        # ── COMMIT here ── other workers can now see status = 'processing'

    logger.info(
        "process_single_payout: payout %s → processing (attempt %d)",
        payout_id,
        payout.attempts,
    )

    # ── Simulate bank settlement ───────────────────────────────────────── #
    r = random.random()
    if r < 0.70:
        outcome = "success"
    elif r < 0.90:
        outcome = "failure"
    else:
        outcome = "hung"    # simulate timeout / no response

    logger.info("process_single_payout: payout %s outcome=%s", payout_id, outcome)

    # ── Tx2a: success ─────────────────────────────────────────────────── #
    if outcome == "success":
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)
            payout.transition_to(Payout.COMPLETED)
            payout.save()
            # No ledger change: the DEBIT posted at request time is the final record.

    # ── Tx2b: failure (status + credit reversal — both or neither) ──────── #
    elif outcome == "failure":
        with transaction.atomic():
            payout = Payout.objects.select_for_update().get(id=payout_id)
            payout.transition_to(Payout.FAILED)
            payout.failure_reason = "Bank declined"
            payout.save()
            # ATOMICALLY return the held funds to the merchant's ledger.
            # If this INSERT fails the status update above is also rolled back.
            LedgerEntry.objects.create(
                merchant=payout.merchant,
                entry_type="CREDIT",
                amount_paise=payout.amount_paise,
                reference_id=str(payout.id),
                description="Payout reversal: bank declined",
            )

    # ── outcome == 'hung': do nothing ─────────────────────────────────── #
    # retry_stuck_payouts will find this payout after 30 s and either
    # reset it to 'pending' (for another attempt) or permanently fail it.

    return f"Payout {payout_id}: outcome={outcome}"


# ────────────────────────────────────────────────────────────────────────────
# Task 3: retry_stuck_payouts
# ────────────────────────────────────────────────────────────────────────────

@shared_task(name="payouts.tasks.retry_stuck_payouts")
def retry_stuck_payouts():
    """
    Periodic task (every 30 s).

    Finds payouts stuck in 'processing' for more than 30 seconds and
    either permanently fails them (if attempts >= 3) or resets them
    back to 'pending' for another attempt.

    The fund-return (CREDIT entry) and the status → 'failed' transition
    are always wrapped in the SAME atomic block so they are both-or-neither.
    """
    from .models import Payout
    from merchants.models import LedgerEntry

    cutoff = timezone.now() - timedelta(seconds=30)

    stuck_ids = list(
        Payout.objects.filter(
            status=Payout.PROCESSING,
            processing_started_at__lt=cutoff,
        )
        .only("id")
        .values_list("id", flat=True)
    )

    handled = 0
    for payout_id in stuck_ids:
        with transaction.atomic():
            # Re-fetch and lock inside the transaction so we don't race with
            # a worker that just finished settling the payout.
            try:
                payout = Payout.objects.select_for_update().get(id=payout_id)
            except Payout.DoesNotExist:
                continue

            # Re-check conditions inside the lock.
            if (
                payout.status != Payout.PROCESSING
                or payout.processing_started_at is None
                or payout.processing_started_at >= cutoff
            ):
                continue  # Another worker already handled it

            if payout.attempts >= 3:
                with transaction.atomic():
                    # ── Permanently fail: status + credit reversal in one tx ── #
                    payout.transition_to(Payout.FAILED)
                    payout.failure_reason = "Max retries exceeded"
                    payout.save()
                    LedgerEntry.objects.create(
                        merchant=payout.merchant,
                        entry_type="CREDIT",
                        amount_paise=payout.amount_paise,
                        reference_id=str(payout.id),
                        description="Payout reversal: max retries exceeded",
                    )
                    logger.warning(
                        "retry_stuck_payouts: payout %s permanently failed (max retries)",
                        payout_id,
                    )
            else:
                # ── Reset to pending for another attempt ───────────────── #
                # Direct assignment (not transition_to) — this is an intentional
                # retry reset, not a forward state-machine transition.
                payout.status = Payout.PENDING
                payout.processing_started_at = None
                payout.save()
                logger.info(
                    "retry_stuck_payouts: payout %s reset to pending (attempt %d)",
                    payout_id,
                    payout.attempts,
                )

            handled += 1

    logger.info("retry_stuck_payouts: handled %d stuck payout(s)", handled)
    return f"Handled {handled} stuck payout(s)"
