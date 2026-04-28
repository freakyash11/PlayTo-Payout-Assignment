from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import PayoutViewSet

router = DefaultRouter(trailing_slash=True)
router.register(r"", PayoutViewSet, basename="payout")

urlpatterns = [
    path("", include(router.urls)),
]
