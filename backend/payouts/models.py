import uuid

from django.db import models


class Payout(models.Model):
    # ------------------------------------------------------------------ #
    # Status choices                                                        #
    # ------------------------------------------------------------------ #
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

    STATUS_CHOICES = [
        (PENDING, "Pending"),
        (PROCESSING, "Processing"),
        (COMPLETED, "Completed"),
        (FAILED, "Failed"),
    ]

    # Explicit allowlist of legal status transitions.
    # Any pair not present here is forbidden.
    ALLOWED_TRANSITIONS: dict[str, list[str]] = {
        PENDING: [PROCESSING],
        PROCESSING: [COMPLETED, FAILED],
        COMPLETED: [],
        FAILED: [],
    }

    # ------------------------------------------------------------------ #
    # Fields                                                                #
    # ------------------------------------------------------------------ #
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="payouts",
    )
    # Stored in paise (integer). Never FloatField, never DecimalField.
    amount_paise = models.BigIntegerField()
    bank_account_id = models.CharField(max_length=100)
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default=PENDING,
        db_index=True,
    )
    idempotency_key = models.CharField(max_length=255)
    attempts = models.IntegerField(default=0)
    failure_reason = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    processing_started_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Payout"
        verbose_name_plural = "Payouts"
        unique_together = [("merchant", "idempotency_key")]
        indexes = [
            models.Index(fields=["merchant", "status"]),
        ]

    def __str__(self) -> str:
        return (
            f"Payout {self.id} | {self.merchant_id} | "
            f"₹{self.amount_paise / 100:.2f} | {self.status}"
        )

    # ------------------------------------------------------------------ #
    # State machine                                                         #
    # ------------------------------------------------------------------ #
    def transition_to(self, new_status: str) -> None:
        """Validate and apply a status transition **in memory only**.

        The caller is responsible for persisting the change inside a
        database transaction. This method intentionally does NOT call
        self.save() so that the caller controls atomicity.

        Raises:
            ValueError: If the transition is not in ALLOWED_TRANSITIONS.
        """
        allowed = self.ALLOWED_TRANSITIONS.get(self.status, [])
        if new_status not in allowed:
            raise ValueError(
                f"Illegal transition: {self.status} -> {new_status}"
            )
        self.status = new_status


class IdempotencyRecord(models.Model):
    """Stores the serialised API response for a previously seen idempotency key.

    When a duplicate request arrives (same merchant + idempotency_key),
    the view layer returns the cached response_body directly without
    re-processing the payout.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    merchant = models.ForeignKey(
        "merchants.Merchant",
        on_delete=models.PROTECT,
        related_name="idempotency_records",
    )
    idempotency_key = models.CharField(max_length=255)
    # Exact serialised JSON response returned to the client
    response_body = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "Idempotency Record"
        verbose_name_plural = "Idempotency Records"
        unique_together = [("merchant", "idempotency_key")]

    def __str__(self) -> str:
        return f"IdempotencyRecord [{self.idempotency_key}] – {self.merchant_id}"
