from django.contrib.auth import views as auth_views
from django.urls import path

from .views import RoleLoginView

app_name = "accounts"

urlpatterns = [
    path("login/", RoleLoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
]
