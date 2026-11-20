from django.urls import path

from . import views

urlpatterns = [
    path("v1/auth/login/", views.LoginAPIView.as_view(), name="api-auth-login"),
    path("v1/auth/refresh/", views.RefreshAPIView.as_view(), name="api-auth-refresh"),
    path("v1/auth/logout/", views.LogoutAPIView.as_view(), name="api-auth-logout"),
    path("v1/accounts/me/", views.MeAPIView.as_view(), name="api-accounts-me"),
    path("v1/accounts/agents/", views.AgentListAPIView.as_view(), name="api-accounts-agents"),
    path("token/", views.LoginAPIView.as_view(), name="api-token-obtain"),
    path("token/refresh/", views.RefreshAPIView.as_view(), name="api-token-refresh"),
]
