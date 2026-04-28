from rest_framework import serializers

from .models import Payout


class PayoutSerializer(serializers.ModelSerializer):
    """
    Read-only serializer used for responses.

    merchant_id is declared as an explicit CharField so that DRF always
    coerces the UUID FK value to a str during to_representation().
    This keeps response_body entirely JSON-safe when stored in IdempotencyRecord.JSONField.
    """

    # CharField.to_representation() calls str() on the value, so the raw
    # uuid.UUID FK attribute is safely coerced to a string — no source= needed.
    merchant_id = serializers.CharField(read_only=True)

    class Meta:
        model = Payout
        fields = [
            "id",
            "merchant_id",
            "amount_paise",
            "bank_account_id",
            "status",
            "idempotency_key",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields
