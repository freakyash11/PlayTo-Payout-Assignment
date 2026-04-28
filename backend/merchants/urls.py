from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import MerchantViewSet

router = DefaultRouter(trailing_slash=True)
router.register(r"", MerchantViewSet, basename="merchant")

urlpatterns = [
    path("", include(router.urls)),
]
