from django.urls import include, path
from rest_framework.routers import DefaultRouter

from .views import CategoryViewSet

router = DefaultRouter()
router.register("v1/categories", CategoryViewSet, basename="api-v1-category")
router.register("categories", CategoryViewSet, basename="api-category")

urlpatterns = [
    path("", include(router.urls)),
]
