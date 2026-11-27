from django.contrib.auth import views as auth_views
from django.urls import reverse

from .models import User


class RoleLoginView(auth_views.LoginView):
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def get_default_redirect_url(self):
        user = self.request.user
        if isinstance(user, User) and (user.role == User.Role.MANAGER or user.is_staff):
            return reverse("tickets:manage_stats")
        return reverse("tickets:list")
