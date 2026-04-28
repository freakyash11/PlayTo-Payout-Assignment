import threading
import uuid
import pytest
from django.test import TestCase
from django.urls import reverse
from rest_framework.test import APIClient
from merchants.models import Merchant, LedgerEntry
from payouts.models import Payout


@pytest.mark.django_db(transaction=True)
def test_concurrent_payouts_prevent_overdraft():
    """
    Merchant has 10000 paise (₹100).
    Two simultaneous 6000 paise (₹60) payout requests fire at the same time.
    Exactly one must succeed (201), one must fail (402 insufficient_funds).
    Only one Payout object must exist in DB after both requests complete.
    """
    # Setup merchant with 10000 paise
    merchant = Merchant.objects.create(
        name="Test Merchant",
        email="test@merchant.com",
        bank_account_id="TESTBANK001",
    )
    LedgerEntry.objects.create(
        merchant=merchant,
        entry_type="CREDIT",
        amount_paise=10000,
        reference_id="seed-001",
        description="Initial credit",
    )

    client1 = APIClient()
    client2 = APIClient()

    results = {}
    barrier = threading.Barrier(2)

    def make_request(client, key, result_key):
        barrier.wait()  # Both threads hit the view at the same time
        response = client.post(
            "/api/v1/payouts/",
            data={"amount_paise": 6000, "bank_account_id": "TESTBANK001"},
            format="json",
            headers={
                "X-Merchant-Id": str(merchant.id),
                "Idempotency-Key": key,
            },
        )
        results[result_key] = response.status_code

    key1 = str(uuid.uuid4())
    key2 = str(uuid.uuid4())

    t1 = threading.Thread(target=make_request, args=(client1, key1, "r1"))
    t2 = threading.Thread(target=make_request, args=(client2, key2, "r2"))

    t1.start()
    t2.start()
    t1.join()
    t2.join()

    status_codes = sorted(results.values())

    # Exactly one 201 and one 402
    assert status_codes == [201, 402], (
        f"Expected [201, 402] but got {status_codes}. "
        "Race condition allowed overdraft!"
    )

    # Only one payout created
    assert Payout.objects.filter(merchant=merchant).count() == 1, (
        "Two payouts were created — double spend occurred!"
    )

    # Only one debit ledger entry
    assert LedgerEntry.objects.filter(
        merchant=merchant, entry_type="DEBIT"
    ).count() == 1, "Two debit entries created — funds debited twice!"