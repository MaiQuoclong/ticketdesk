from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db.models import Count, ProtectedError, Q
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.models import User

from .forms import CommentForm, TicketForm
from .models import Category, Ticket, TicketHistory
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


def _check_manager(request: HttpRequest) -> bool:
    return request.user.is_authenticated and (
        request.user.role == User.Role.MANAGER or request.user.is_staff
    )


@login_required
def manage_users_view(request: HttpRequest) -> HttpResponse:
    if not _check_manager(request):
        messages.error(request, "Chỉ Quản lý hoặc Admin mới có quyền quản lý người dùng.")
        return redirect("tickets:list")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create_user":
            username = (request.POST.get("username") or "").strip()
            email = (request.POST.get("email") or "").strip()
            password = request.POST.get("password") or ""
            role = request.POST.get("role") or User.Role.CUSTOMER
            if not username or not password:
                messages.error(request, "Vui lòng nhập đầy đủ tên đăng nhập và mật khẩu.")
            elif User.objects.filter(username=username).exists():
                messages.error(request, f"Tài khoản '{username}' đã tồn tại.")
            else:
                User.objects.create_user(
                    username=username,
                    email=email,
                    password=password,
                    role=role if role in User.Role.values else User.Role.CUSTOMER,
                    is_staff=(role == User.Role.MANAGER),
                )
                messages.success(request, f"Đã tạo tài khoản '{username}' thành công!")
        elif action == "update_user":
            user_id = request.POST.get("user_id")
            target = get_object_or_404(User, pk=user_id)
            new_role = request.POST.get("role")
            is_active = request.POST.get("is_active") == "on"
            if new_role in User.Role.values:
                target.role = new_role
            if target != request.user:
                target.is_active = is_active
            target.save(update_fields=["role", "is_active"])
            messages.success(request, f"Đã cập nhật quyền cho tài khoản '{target.username}'.")
        return redirect("tickets:manage_users")

    users = User.objects.annotate(
        created_count=Count("created_tickets", distinct=True),
        assigned_count=Count("assigned_tickets", distinct=True),
    ).order_by("-date_joined")
    return render(
        request,
        "tickets/manage_users.html",
        {"users_list": users, "role_choices": User.Role.choices},
    )


@login_required
def manage_categories_view(request: HttpRequest) -> HttpResponse:
    if not _check_manager(request):
        messages.error(request, "Chỉ Quản lý hoặc Admin mới có quyền quản lý danh mục.")
        return redirect("tickets:list")

    if request.method == "POST":
        action = request.POST.get("action")
        if action == "create":
            name = (request.POST.get("name") or "").strip()
            description = (request.POST.get("description") or "").strip()
            if not name:
                messages.error(request, "Tên danh mục không được để trống.")
            elif Category.objects.filter(name__iexact=name).exists():
                messages.error(request, f"Danh mục '{name}' đã tồn tại.")
            else:
                Category.objects.create(name=name, description=description)
                messages.success(request, f"Đã thêm danh mục '{name}'.")
        elif action == "update":
            cat = get_object_or_404(Category, pk=request.POST.get("category_id"))
            name = (request.POST.get("name") or "").strip()
            description = (request.POST.get("description") or "").strip()
            if name:
                cat.name = name
                cat.description = description
                cat.save(update_fields=["name", "description"])
                messages.success(request, f"Đã cập nhật danh mục '{cat.name}'.")
        elif action == "delete":
            cat = get_object_or_404(Category, pk=request.POST.get("category_id"))
            try:
                cat_name = cat.name
                cat.delete()
                messages.success(request, f"Đã xóa danh mục '{cat_name}'.")
            except ProtectedError:
                messages.error(
                    request,
                    f"Không thể xóa danh mục '{cat.name}' vì đang có ticket "
                    "tham chiếu (ràng buộc PROTECT).",
                )
        return redirect("tickets:manage_categories")

    categories = Category.objects.annotate(ticket_count=Count("tickets")).order_by("name")
    return render(request, "tickets/manage_categories.html", {"categories": categories})


@login_required
def manage_history_view(request: HttpRequest) -> HttpResponse:
    if not _check_manager(request):
        messages.error(request, "Chỉ Quản lý hoặc Admin mới có quyền tra cứu nhật ký hệ thống.")
        return redirect("tickets:list")

    q = (request.GET.get("q") or "").strip()
    histories = TicketHistory.objects.select_related("ticket", "actor").order_by("-created_at")
    if q:
        histories = histories.filter(
            Q(ticket__title__icontains=q)
            | Q(actor__username__icontains=q)
            | Q(field__icontains=q)
            | Q(new_value__icontains=q)
        )
    return render(
        request,
        "tickets/manage_history.html",
        {"histories": histories[:100], "current_q": q},
    )
