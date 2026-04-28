"""
merchants/views.py
==================
GET /api/v1/merchants/me/          — merchant profile + live balance
GET /api/v1/merchants/me/ledger/   — paginated LedgerEntry list (page_size=20)
GET /api/v1/merchants/me/payouts/  — payouts for this merchant (reuses PayoutSerializer)
GET /api/v1/merchants/list/        — all merchants (id + name) for dev switcher

Authentication: X-Merchant-ID header (UUID) on all /me/* endpoints.
/list/ is intentionally unauthenticated — development convenience only.
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from .models import LedgerEntry, Merchant
from .serializers import LedgerEntrySerializer, MerchantListSerializer, MerchantSerializer


# ────────────────────────────────────────────────────────────────────────────
# Pagination
# ────────────────────────────────────────────────────────────────────────────

class LedgerPagination(PageNumberPagination):
    """Page-based pagination for the ledger endpoint."""
    page_size = 20
    page_size_query_param = "page_size"  # ?page_size=N override (max 100)
    max_page_size = 100


# ────────────────────────────────────────────────────────────────────────────
# ViewSet
# ────────────────────────────────────────────────────────────────────────────

class MerchantViewSet(viewsets.ViewSet):
    """
    ViewSet with no DRF authentication/permission classes.
    Merchant identity is established via the X-Merchant-ID header.
    """

    authentication_classes = []
    permission_classes = []

    # ------------------------------------------------------------------ #
    # Private helper                                                        #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _resolve_merchant(request):
        """
        Read X-Merchant-ID header, return (Merchant, error_Response).
        Exactly one of the two values will be None.
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

    # ------------------------------------------------------------------ #
    # Endpoints                                                             #
    # ------------------------------------------------------------------ #

    @action(detail=False, methods=["get"], url_path="me")
    def me(self, request):
        """
        GET /api/v1/merchants/me/
        Returns merchant profile with a live balance breakdown.

        Response:
          {
            "id": "...",
            "name": "...",
            "email": "...",
            "bank_account_id": "...",
            "balance": {
              "net_balance_paise": 500000,
              "held_paise": 60000,
              "available_paise": 440000
            }
          }
        """
        merchant, err = self._resolve_merchant(request)
        if err:
            return err

        return Response(MerchantSerializer(merchant).data)

    @action(detail=False, methods=["get"], url_path="me/ledger")
    def ledger(self, request):
        """
        GET /api/v1/merchants/me/ledger/
        Returns a paginated list of LedgerEntry for this merchant, newest first.
        Page size: 20 (override with ?page_size=N, max 100).

        Response (DRF PageNumberPagination envelope):
          {
            "count": 42,
            "next": "http://.../me/ledger/?page=2",
            "previous": null,
            "results": [ { id, entry_type, amount_paise, reference_id, description, created_at }, ... ]
          }
        """
        merchant, err = self._resolve_merchant(request)
        if err:
            return err

        entries = merchant.ledger_entries.order_by("-created_at")
        paginator = LedgerPagination()
        page = paginator.paginate_queryset(entries, request)
        serializer = LedgerEntrySerializer(page, many=True)
        return paginator.get_paginated_response(serializer.data)

    @action(detail=False, methods=["get"], url_path="me/payouts")
    def payouts(self, request):
        """
        GET /api/v1/merchants/me/payouts/
        Alias for GET /api/v1/payouts/ filtered to this merchant.
        Reuses PayoutSerializer to keep the response shape identical.
        """
        merchant, err = self._resolve_merchant(request)
        if err:
            return err

        # Local imports to avoid circular dependency at module level.
        from payouts.models import Payout
        from payouts.serializers import PayoutSerializer

        qs = Payout.objects.filter(merchant=merchant).order_by("-created_at")
        return Response(PayoutSerializer(qs, many=True).data)

    @action(detail=False, methods=["get"], url_path="list")
    def list_all(self, request):
        """
        GET /api/v1/merchants/list/
        Returns all merchants as [{id, name}].
        Intentionally unauthenticated — used only by the dev frontend
        merchant switcher so testers can change merchant context without
        logging in.  Expose ONLY id and name, never email or bank details.
        """
        merchants = Merchant.objects.all().order_by("name")
        return Response(MerchantListSerializer(merchants, many=True).data)
