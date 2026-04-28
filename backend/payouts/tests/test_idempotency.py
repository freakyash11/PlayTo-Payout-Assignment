import uuid
import pytest
from rest_framework.test import APIClient
from merchants.models import Merchant, LedgerEntry
from payouts.models import Payout


@pytest.mark.django_db(transaction=True)
def test_same_idempotency_key_returns_same_response():
    """
    Two requests with the same idempotency key must:
    - Both return 200 or 201
    - Return identical response bodies (same payout ID)
    - Create only one Payout in DB
    - Create only one DEBIT LedgerEntry
    """
    merchant = Merchant.objects.create(
        name="Idempotency Merchant",
        email="idempotency@test.com",
        bank_account_id="IDEM001",
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        entry_type="CREDIT",
        amount_paise=100000,
        reference_id="seed-idem",
        description="Initial credit",
    )

    client = APIClient()
    idempotency_key = str(uuid.uuid4())

    headers = {
        "X-Merchant-Id": str(merchant.id),
        "Idempotency-Key": idempotency_key,
    }

    response1 = client.post(
        "/api/v1/payouts/",
        data={"amount_paise": 5000, "bank_account_id": "IDEM001"},
        format="json",
        headers=headers,
    )

    response2 = client.post(
        "/api/v1/payouts/",
        data={"amount_paise": 5000, "bank_account_id": "IDEM001"},
        format="json",
        headers=headers,
    )

    assert response1.status_code in [200, 201]
    assert response2.status_code in [200, 201]

    # Same payout ID returned both times
    assert response1.data["id"] == response2.data["id"], (
        "Different payout IDs returned — idempotency broken!"
    )

    # Only one payout created
    assert Payout.objects.filter(merchant=merchant).count() == 1, (
        "Two payouts created for same idempotency key!"
    )

    # Only one debit entry
    assert LedgerEntry.objects.filter(
        merchant=merchant, entry_type="DEBIT"
    ).count() == 1, "Two debit entries created — funds held twice!"


@pytest.mark.django_db
def test_illegal_state_transition():
    """completed → pending must raise ValueError"""
    from payouts.models import Payout
    p = Payout()
    p.status = "completed"
    try:
        p.transition_to("pending")
        assert False, "Should have raised ValueError"
    except ValueError:
        pass


@pytest.mark.django_db(transaction=True)
def test_failed_payout_returns_funds():
    """
    When a payout fails, the CREDIT reversal must exist
    and merchant balance must be restored.
    """
    merchant = Merchant.objects.create(
        name="Refund Merchant",
        email="refund@test.com",
        bank_account_id="REFUND001",
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        entry_type="CREDIT",
        amount_paise=50000,
        reference_id="seed-refund",
        description="Initial credit",
    )

    # Create payout and hold funds (debit)
    payout = Payout.objects.create(
        merchant=merchant,
        amount_paise=30000,
        bank_account_id="REFUND001",
        status=Payout.PENDING,
        idempotency_key=str(uuid.uuid4()),
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        entry_type="DEBIT",
        amount_paise=30000,
        reference_id=str(payout.id),
        description="Payout hold",
    )

    # Simulate failure path
    # Simulate failure path — must go pending → processing → failed
    from django.db import transaction
    with transaction.atomic():
        payout.transition_to(Payout.PROCESSING)
        payout.save()

    with transaction.atomic():
        payout.transition_to(Payout.FAILED)
        payout.failure_reason = "Bank declined"
        payout.save()
        LedgerEntry.objects.create(
            merchant=merchant,
            entry_type="CREDIT",
            amount_paise=30000,
            reference_id=str(payout.id),
            description="Payout reversal: bank declined",
        )

    # Payout is failed
    payout.refresh_from_db()
    assert payout.status == Payout.FAILED

    # Funds returned
    breakdown = merchant.get_balance_breakdown()
    assert breakdown["available_paise"] == 50000, (
        f"Expected 50000 but got {breakdown['available_paise']} — funds not returned!"
    )