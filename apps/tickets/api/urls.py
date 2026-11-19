from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet, TicketViewSet

router = DefaultRouter()
router.register("v1/categories", CategoryViewSet, basename="api-v1-category")
router.register("categories", CategoryViewSet, basename="api-category")
router.register("v1/tickets", TicketViewSet, basename="api-v1-ticket")
router.register("tickets", TicketViewSet, basename="api-ticket")

urlpatterns = [
    path("", include(router.urls)),
]
