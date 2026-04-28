import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = []

    operations = [
        migrations.CreateModel(
            name="Merchant",
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
                ("name", models.CharField(max_length=255)),
                ("email", models.EmailField(max_length=254, unique=True)),
                ("bank_account_id", models.CharField(max_length=100)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Merchant",
                "verbose_name_plural": "Merchants",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="LedgerEntry",
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
                        related_name="ledger_entries",
                        to="merchants.merchant",
                    ),
                ),
                (
                    "entry_type",
                    models.CharField(
                        choices=[("CREDIT", "credit"), ("DEBIT", "debit")],
                        max_length=6,
                    ),
                ),
                ("amount_paise", models.BigIntegerField()),
                ("reference_id", models.CharField(max_length=255)),
                ("description", models.CharField(blank=True, max_length=500)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "verbose_name": "Ledger Entry",
                "verbose_name_plural": "Ledger Entries",
                "ordering": ["-created_at"],
            },
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(
                fields=["merchant", "entry_type"],
                name="merchants_l_merchan_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="ledgerentry",
            index=models.Index(
                fields=["reference_id"],
                name="merchants_l_ref_id_idx",
            ),
        ),
    ]
