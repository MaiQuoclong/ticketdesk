from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.models import User

from .forms import CommentForm, TicketForm
from .models import Category, Ticket
from .services import (
    TicketServiceError,
    add_comment,
    assign_ticket,
    change_ticket_status,
)


class TicketQuerysetMixin:
    """Phân quyền dữ liệu trong get_queryset: Khách hàng chỉ thấy ticket của mình."""

    request: HttpRequest

    def get_queryset(self):
        qs = Ticket.objects.select_related("category", "assignee", "created_by")
        user = self.request.user
        if user.is_authenticated and user.role == User.Role.CUSTOMER:
            qs = qs.filter(created_by=user)
        return qs


class TicketListView(LoginRequiredMixin, TicketQuerysetMixin, ListView):
    model = Ticket
    template_name = "tickets/ticket_list.html"
    context_object_name = "tickets"
    paginate_by = 20

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get("status")
        priority = self.request.GET.get("priority")
        category = self.request.GET.get("category")
        q = (self.request.GET.get("q") or "").strip()

        if status in Ticket.Status.values:
            qs = qs.filter(status=status)
        if priority and priority.isdigit():
            qs = qs.filter(priority=int(priority))
        if category:
            qs = qs.filter(category_id=category)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        return qs

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_qs = super().get_queryset()
        counts = dict(
            base_qs.values_list("status").annotate(total=Count("id")).values_list("status", "total")
        )
        total_all = sum(counts.values())
        resolved_count = counts.get(Ticket.Status.RESOLVED, 0) + counts.get(
            Ticket.Status.CLOSED, 0
        )
        ctx["stats"] = {
            "total": total_all,
            "new": counts.get(Ticket.Status.NEW, 0),
            "in_progress": counts.get(Ticket.Status.IN_PROGRESS, 0),
            "resolved": resolved_count,
            "resolved_pct": int((resolved_count / total_all) * 100) if total_all else 0,
        }
        ctx["categories"] = Category.objects.all()
        ctx["status_choices"] = Ticket.Status.choices
        ctx["priority_choices"] = Ticket.Priority.choices
        ctx["current_status"] = self.request.GET.get("status", "")
        ctx["current_priority"] = self.request.GET.get("priority", "")
        ctx["current_q"] = self.request.GET.get("q", "")
        ctx["agents"] = User.objects.filter(role=User.Role.AGENT, is_active=True)[:6]
        return ctx


class TicketDetailView(LoginRequiredMixin, TicketQuerysetMixin, DetailView):
    model = Ticket
    template_name = "tickets/ticket_detail.html"
    context_object_name = "ticket"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        comments_qs = self.object.comments.select_related("author")
        if self.request.user.role == User.Role.CUSTOMER:
            comments_qs = comments_qs.filter(is_internal=False)
        ctx["comments"] = comments_qs
        ctx["histories"] = self.object.histories.select_related("actor")[:20]
        ctx["comment_form"] = CommentForm()
        ctx["status_choices"] = Ticket.Status.choices
        if self.request.user.role == User.Role.MANAGER:
            ctx["agents"] = User.objects.filter(role=User.Role.AGENT, is_active=True)
        return ctx


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    form_class = TicketForm
    template_name = "tickets/ticket_form.html"
    success_url = reverse_lazy("tickets:list")

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        messages.success(self.request, "Tạo ticket mới thành công!")
        return super().form_valid(form)


class TicketUpdateView(LoginRequiredMixin, TicketQuerysetMixin, UpdateView):
    model = Ticket
    form_class = TicketForm
    template_name = "tickets/ticket_form.html"

    def get_success_url(self):
        messages.success(self.request, "Đã cập nhật thông tin ticket.")
        return reverse_lazy("tickets:detail", kwargs={"pk": self.object.pk})


def _get_accessible_ticket(request: HttpRequest, pk) -> Ticket:
    qs = Ticket.objects.select_related("category", "assignee", "created_by")
    if request.user.role == User.Role.CUSTOMER:
        qs = qs.filter(created_by=request.user)
    ticket = qs.filter(pk=pk).first()
    if not ticket:
        raise Http404("Không tìm thấy ticket.")
    return ticket


@login_required
@require_POST
def ticket_assign_view(request: HttpRequest, pk) -> HttpResponse:
    if request.user.role != User.Role.MANAGER:
        messages.error(request, "Chỉ Quản lý mới có quyền gán người xử lý.")
        return redirect("tickets:detail", pk=pk)

    ticket = _get_accessible_ticket(request, pk)
    agent_id = request.POST.get("agent_id")
    agent = get_object_or_404(User, pk=agent_id, role=User.Role.AGENT)
    try:
        assign_ticket(ticket=ticket, agent=agent, actor=request.user)
        messages.success(request, f"Đã gán ticket cho nhân viên {agent.username}.")
    except TicketServiceError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def ticket_status_view(request: HttpRequest, pk) -> HttpResponse:
    if request.user.role == User.Role.CUSTOMER:
        messages.error(request, "Khách hàng không được tự đổi trạng thái xử lý.")
        return redirect("tickets:detail", pk=pk)

    ticket = _get_accessible_ticket(request, pk)
    new_status = request.POST.get("status", "")
    try:
        change_ticket_status(ticket=ticket, new_status=new_status, actor=request.user)
        messages.success(
            request, f"Đã chuyển trạng thái sang {ticket.get_status_display()}."
        )
    except TicketServiceError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def ticket_comment_view(request: HttpRequest, pk) -> HttpResponse:
    ticket = _get_accessible_ticket(request, pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        try:
            add_comment(
                ticket=ticket,
                author=request.user,
                content=form.cleaned_data["content"],
                is_internal=form.cleaned_data.get("is_internal", False),
            )
            messages.success(request, "Đã gửi bình luận.")
        except TicketServiceError as exc:
            messages.error(request, str(exc))
    else:
        messages.error(request, "Nội dung bình luận không hợp lệ.")
    return redirect("tickets:detail", pk=pk)
