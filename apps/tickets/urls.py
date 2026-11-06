from django.urls import path

from . import views

app_name = "tickets"

urlpatterns = [
    path("", views.TicketListView.as_view(), name="list"),
    path("new/", views.TicketCreateView.as_view(), name="create"),
    path("<uuid:pk>/", views.TicketDetailView.as_view(), name="detail"),
    path("<uuid:pk>/edit/", views.TicketUpdateView.as_view(), name="edit"),
    path("<uuid:pk>/assign/", views.ticket_assign_view, name="assign"),
    path("<uuid:pk>/status/", views.ticket_status_view, name="change_status"),
    path("<uuid:pk>/comment/", views.ticket_comment_view, name="add_comment"),
]
