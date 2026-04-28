from django.apps import AppConfig


class PayoutsConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "payouts"
    verbose_name = "Payouts"

    def ready(self):
        import payouts.tasks  # noqa: F401 — ensures tasks are registered with Celery