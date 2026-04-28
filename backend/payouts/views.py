"""
payouts/views.py
================
POST /api/v1/payouts/  — request a payout (idempotent)
GET  /api/v1/payouts/  — list payouts for this merchant
GET  /api/v1/payouts/{id}/  — retrieve one payout

Authentication: X-Merchant-ID header (UUID of the merchant).
Idempotency:    Idempotency-Key header (UUID string, required on POST).
"""

from datetime import timedelta

import uuid

from django.db import IntegrityError, transaction
from django.utils import timezone
from rest_framework import status, viewsets
from rest_framework.response import Response

from merchants.models import LedgerEntry, Merchant
from .models import IdempotencyRecord, Payout
from .serializers import PayoutSerializer


class PayoutViewSet(viewsets.ViewSet):
    """
    ViewSet with no DRF authentication/permission classes — merchant identity
    is established via the X-Merchant-ID header inside each action.
    """

    authentication_classes = []
    permission_classes = []

    # Idempotency keys older than this are treated as expired.
    # A new request with the same key after the TTL creates a fresh payout.
    # Industry standard (e.g. Stripe) is 24 hours.
    IDEMPOTENCY_KEY_TTL_HOURS = 24

    # ------------------------------------------------------------------ #
    # Private helpers                                                       #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve_merchant(request):
        """
        Read X-Merchant-ID header, return (Merchant, error_Response).
        Exactly one of the two return values will be None.
        """
        merchant_id = request.headers.get("X-Merchant-Id")
        if not merchant_id:
            return None, Response(
                {"error": "X-Merchant-ID header is required."},
                status=status.HTTP_401_UNAUTHORIZED,
            )
        try:
            merchant = Merchant.objects.get(id=merchant_id)
        except (Merchant.DoesNotExist, ValueError):
            return None, Response(
                {"error": "Merchant not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        return merchant, None

    @staticmethod
    def _resolve_idempotency_key(request):
        """
        Read Idempotency-Key header; validate it is a UUID.
        Return (key_str, error_Response). Exactly one will be None.
        """
        key = request.headers.get("Idempotency-Key")
        if not key:
            return None, Response(
                {"error": "Idempotency-Key header is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            uuid.UUID(key)          # validates format; we store the original string
        except ValueError:
            return None, Response(
                {"error": "Idempotency-Key must be a valid UUID."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        return key, None

    # ------------------------------------------------------------------ #
    # Actions                                                               #
    # ------------------------------------------------------------------ #

    def list(self, request):
        """GET /api/v1/payouts/ — list all payouts for the authenticated merchant."""
        merchant, err = self._resolve_merchant(request)
        if err:
            return err

        payouts = Payout.objects.filter(merchant=merchant).order_by("-created_at")
        serializer = PayoutSerializer(payouts, many=True)
        return Response(serializer.data)

    def retrieve(self, request, pk=None):
        """GET /api/v1/payouts/{id}/ — retrieve a single payout."""
        merchant, err = self._resolve_merchant(request)
        if err:
            return err

        try:
            payout = Payout.objects.get(id=pk, merchant=merchant)
        except (Payout.DoesNotExist, ValueError):
            return Response(
                {"error": "Payout not found."},
                status=status.HTTP_404_NOT_FOUND,
            )

        return Response(PayoutSerializer(payout).data)

    def create(self, request):
        """
        POST /api/v1/payouts/ — request a new payout.

        Step 1 — Idempotency check (no lock yet).
        Step 2 — Inside a single atomic transaction:
            a) SELECT FOR UPDATE on the merchant row  ← prevents double-spend
            b) Derive available balance via DB aggregation (inside the lock)
            c) 402 if insufficient funds
            d) Create Payout (status='pending')
            e) Create DEBIT LedgerEntry to hold the funds
            f) Serialise the payout
            g) Persist IdempotencyRecord
        Step 3 — Return 201.
        """
        # ── Resolve merchant identity ──────────────────────────────────── #
        merchant, err = self._resolve_merchant(request)
        if err:
            return err

        # ── Validate Idempotency-Key ───────────────────────────────────── #
        idempotency_key, err = self._resolve_idempotency_key(request)
        if err:
            return err

        # ── Step 1: Idempotency check — BEFORE acquiring any lock ─────── #
        # Only replay responses within the TTL window.  A key older than
        # IDEMPOTENCY_KEY_TTL_HOURS is treated as expired: the caller gets a
        # fresh payout, which prevents stale 'pending' snapshots being
        # replayed long after the payout completed or failed.
        ttl_cutoff = timezone.now() - timedelta(hours=self.IDEMPOTENCY_KEY_TTL_HOURS)
        try:
            record = IdempotencyRecord.objects.get(
                merchant=merchant,
                idempotency_key=idempotency_key,
                created_at__gte=ttl_cutoff,
            )
            # Return the exact same response that was sent originally.
            return Response(record.response_body, status=status.HTTP_200_OK)
        except IdempotencyRecord.DoesNotExist:
            pass

        # ── Validate request body ──────────────────────────────────────── #
        amount_paise = request.data.get("amount_paise")
        bank_account_id = request.data.get("bank_account_id")

        if amount_paise is None or bank_account_id is None:
            return Response(
                {"error": "amount_paise and bank_account_id are required."},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if not isinstance(amount_paise, int) or amount_paise <= 0:
            return Response(
                {"error": "amount_paise must be a positive integer (paise)."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # ── Step 2: Single atomic transaction ─────────────────────────── #
        #
        # Race-condition safety: two concurrent requests with the SAME
        # idempotency key can both pass the Step-1 lookup (no row exists yet)
        # and reach this point simultaneously.  The SELECT FOR UPDATE on the
        # merchant row serialises the balance check and the INSERTs, so only
        # one request will commit successfully.  The other will raise an
        # IntegrityError from the unique_together constraint on either Payout
        # or IdempotencyRecord.  We catch that and fall back to the now-
        # committed IdempotencyRecord, returning 200 as if Step 1 had matched.
        try:
            with transaction.atomic():

                # a) Row-level lock on the merchant.
                #    SELECT FOR UPDATE blocks any concurrent transaction that tries
                #    to lock the same merchant row — this is the ONLY correct way
                #    to prevent the double-spend race condition in PostgreSQL.
                #    Python-level locks (threading.Lock, etc.) are NOT sufficient
                #    because they don't span database connections / worker processes.
                merchant = Merchant.objects.select_for_update().get(id=merchant.id)

                # b) Derive available balance using DB aggregation — inside the lock
                #    so that no committed write can slip in between the check and the
                #    subsequent INSERT.
                breakdown = merchant.get_balance_breakdown()
                available_paise = breakdown["available_paise"]

                # c) Insufficient funds → bail out without creating anything.
                if available_paise < amount_paise:
                    return Response(
                        {"error": "insufficient_funds"},
                        status=status.HTTP_402_PAYMENT_REQUIRED,
                    )

                # d) Create the Payout record.
                payout = Payout.objects.create(
                    merchant=merchant,
                    amount_paise=amount_paise,
                    bank_account_id=bank_account_id,
                    status=Payout.PENDING,
                    idempotency_key=idempotency_key,
                )

                # e) Create a DEBIT LedgerEntry that "holds" the funds.
                #    This ensures get_balance_breakdown() will correctly subtract
                #    this amount as "held" in future balance checks.
                LedgerEntry.objects.create(
                    merchant=merchant,
                    entry_type="DEBIT",
                    amount_paise=amount_paise,
                    reference_id=str(payout.id),
                    description="Payout hold",
                )

                # f) Serialise the payout into a plain dict.
                response_data = PayoutSerializer(payout).data

                # g) Persist the IdempotencyRecord so future duplicate requests
                #    get this exact response replayed as HTTP 200.
                IdempotencyRecord.objects.create(
                    merchant=merchant,
                    idempotency_key=idempotency_key,
                    response_body=dict(response_data),
                )

        except IntegrityError:
            # A concurrent request with the same idempotency key committed
            # just before us and already created the Payout + IdempotencyRecord.
            # The transaction above was rolled back automatically by PostgreSQL.
            # Re-fetch the now-committed record and replay the original response.
            try:
                record = IdempotencyRecord.objects.get(
                    merchant=merchant,
                    idempotency_key=idempotency_key,
                    created_at__gte=ttl_cutoff,
                )
                return Response(record.response_body, status=status.HTTP_200_OK)
            except IdempotencyRecord.DoesNotExist:
                # Should be unreachable: IntegrityError must have come from
                # IdempotencyRecord or Payout unique constraint, so the record
                # must exist.  Return 409 as a last resort.
                return Response(
                    {"error": "Concurrent request conflict. Please retry."},
                    status=status.HTTP_409_CONFLICT,
                )

        # h) Commit happened; return 201.
        return Response(response_data, status=status.HTTP_201_CREATED)
