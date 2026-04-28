import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ("merchants", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="Payout",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payouts",
                        to="merchants.merchant",
                    ),
                ),
                ("amount_paise", models.BigIntegerField()),
                ("bank_account_id", models.CharField(max_length=100)),
                (
                    "status",
                    models.CharField(
                        choices=[
                            ("pending", "Pending"),
                            ("processing", "Processing"),
                            ("completed", "Completed"),
                            ("failed", "Failed"),
                        ],
                        db_index=True,
                        default="pending",
                        max_length=20,
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=255)),
                ("attempts", models.IntegerField(default=0)),
                ("failure_reason", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                (
                    "processing_started_at",
                    models.DateTimeField(blank=True, null=True),
                ),
            ],
            options={
                "verbose_name": "Payout",
                "verbose_name_plural": "Payouts",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="IdempotencyRecord",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        default=uuid.uuid4,
                        editable=False,
                        primary_key=True,
                        serialize=False,
                    ),
                ),
                (
                    "merchant",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="idempotency_records",
                        to="merchants.merchant",
                    ),
                ),
                ("idempotency_key", models.CharField(max_length=255)),
                ("response_body", models.JSONField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Idempotency Record",
                "verbose_name_plural": "Idempotency Records",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="payout",
            index=models.Index(
                fields=["merchant", "status"],
                name="payouts_pay_merchant_status_idx",
            ),
        ),
        migrations.AlterUniqueTogether(
            name="payout",
            unique_together={("merchant", "idempotency_key")},
        ),
        migrations.AlterUniqueTogether(
            name="idempotencyrecord",
            unique_together={("merchant", "idempotency_key")},
        ),
    ]
