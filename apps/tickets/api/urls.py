from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import (
    AttachmentViewSet,
    CategoryViewSet,
    DashboardSlaOverdueAPIView,
    DashboardSummaryAPIView,
    TicketViewSet,
)

router = DefaultRouter()
router.register("v1/categories", CategoryViewSet, basename="api-v1-category")
router.register("categories", CategoryViewSet, basename="api-category")
router.register("v1/tickets", TicketViewSet, basename="api-v1-ticket")
router.register("tickets", TicketViewSet, basename="api-ticket")
router.register("v1/attachments", AttachmentViewSet, basename="api-v1-attachment")
router.register("attachments", AttachmentViewSet, basename="api-attachment")

urlpatterns = [
    path(
        "v1/dashboard/summary/",
        DashboardSummaryAPIView.as_view(),
        name="api-v1-dashboard-summary",
    ),
    path(
        "v1/dashboard/sla-overdue/",
        DashboardSlaOverdueAPIView.as_view(),
        name="api-v1-dashboard-sla-overdue",
    ),
    path(
        "dashboard/summary/",
        DashboardSummaryAPIView.as_view(),
        name="api-dashboard-summary",
    ),
    path(
        "dashboard/sla-overdue/",
        DashboardSlaOverdueAPIView.as_view(),
        name="api-dashboard-sla-overdue",
    ),
    path("", include(router.urls)),
]
