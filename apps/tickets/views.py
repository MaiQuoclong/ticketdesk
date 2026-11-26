import uuid
from typing import cast

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Count, IntegerField, OuterRef, ProtectedError, Q, Subquery
from django.db.models.functions import Coalesce
from django.http import FileResponse, Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.cache import patch_vary_headers
from django.views.decorators.http import require_POST
from django.views.generic import CreateView, DetailView, ListView, UpdateView

from apps.accounts.models import User

from . import selectors
from .forms import AttachmentUploadForm, CommentForm, TicketCreateForm, TicketForm
from .models import Attachment, Category, Comment, Ticket, TicketHistory
from .services import (
    TicketServiceError,
    add_comment,
    assign_ticket,
    change_ticket_status,
)


def _parse_uuid(value: str | None) -> uuid.UUID | None:
    if not value:
        return None
    try:
        return uuid.UUID(value)
    except ValueError:
        return None


class TicketQuerysetMixin:
    """Phân quyền dữ liệu trong get_queryset: Khách hàng chỉ thấy ticket của mình."""

    request: HttpRequest

    def get_queryset(self):
        qs = Ticket.objects.select_related("category", "assignee", "created_by")
        user = self.request.user
        if isinstance(user, User) and user.is_authenticated and user.role == User.Role.CUSTOMER:
            qs = qs.filter(created_by=user)
        return qs


class TicketListView(LoginRequiredMixin, TicketQuerysetMixin, ListView):
    model = Ticket
    template_name = "tickets/ticket_list.html"
    partial_template_name = "tickets/_table.html"
    context_object_name = "tickets"
    paginate_by = 20

    def is_htmx_partial(self) -> bool:
        headers = self.request.headers
        return headers.get("HX-Request") == "true" and not headers.get("HX-History-Restore-Request")

    def handle_no_permission(self):
        response = super().handle_no_permission()
        if self.request.headers.get("HX-Request") == "true" and response.status_code == 302:
            return HttpResponse(status=204, headers={"HX-Redirect": response["Location"]})
        return response

    def get_template_names(self):
        if self.is_htmx_partial():
            return [self.partial_template_name]
        return super().get_template_names()

    def render_to_response(self, context, **response_kwargs):
        response = super().render_to_response(context, **response_kwargs)
        patch_vary_headers(response, ["HX-Request"])
        return response

    def get_queryset(self):
        qs = super().get_queryset()
        status = self.request.GET.get("status")
        priority = self.request.GET.get("priority")
        category = self.request.GET.get("category")
        assignee = self.request.GET.get("assignee")
        q = (self.request.GET.get("q") or "").strip()

        if status in Ticket.Status.values:
            qs = qs.filter(status=status)
        if priority and priority.isdigit():
            qs = qs.filter(priority=int(priority))
        category_id = _parse_uuid(category)
        if category_id:
            qs = qs.filter(category_id=category_id)
        if self._can_filter_assignee():
            assignee_id = _parse_uuid(assignee)
            if assignee == "none":
                qs = qs.filter(assignee__isnull=True)
            elif assignee_id:
                qs = qs.filter(assignee_id=assignee_id)
        if q:
            qs = qs.filter(Q(title__icontains=q) | Q(description__icontains=q))
        comments = Comment.objects.filter(ticket=OuterRef("pk"))
        user = self.request.user
        if isinstance(user, User) and user.role == User.Role.CUSTOMER:
            comments = comments.filter(is_internal=False)
        comment_count = comments.order_by().values("ticket").annotate(n=Count("id")).values("n")
        return qs.annotate(
            comment_count=Coalesce(Subquery(comment_count, output_field=IntegerField()), 0)
        )

    def _can_filter_assignee(self) -> bool:
        user = self.request.user
        return isinstance(user, User) and user.role != User.Role.CUSTOMER

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        base_qs = super().get_queryset()
        counts = dict(
            base_qs.values_list("status").annotate(total=Count("id")).values_list("status", "total")
        )
        total_all = sum(counts.values())
        resolved_count = counts.get(Ticket.Status.RESOLVED, 0) + counts.get(Ticket.Status.CLOSED, 0)
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
        ctx["current_assignee"] = self.request.GET.get("assignee", "")
        ctx["can_filter_assignee"] = self._can_filter_assignee()
        if ctx["can_filter_assignee"]:
            ctx["assignee_choices"] = User.objects.filter(
                role=User.Role.AGENT, is_active=True
            ).order_by("username")
        ctx["agents"] = User.objects.filter(role=User.Role.AGENT, is_active=True)[:6]
        return ctx


class TicketDetailView(LoginRequiredMixin, TicketQuerysetMixin, DetailView):
    model = Ticket
    template_name = "tickets/ticket_detail.html"
    context_object_name = "ticket"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = cast(User, self.request.user)
        comments_qs = self.object.comments.select_related("author")
        if user.role == User.Role.CUSTOMER:
            comments_qs = comments_qs.filter(is_internal=False)
        ctx["comments"] = comments_qs
        ctx["histories"] = self.object.histories.select_related("actor")[:20]
        ctx["comment_form"] = CommentForm()
        ctx["attachments"] = self.object.attachments.select_related("uploaded_by").order_by(
            "-created_at"
        )
        ctx["upload_form"] = AttachmentUploadForm()
        ctx["status_choices"] = Ticket.Status.choices
        if user.role == User.Role.MANAGER:
            ctx["agents"] = User.objects.filter(role=User.Role.AGENT, is_active=True)
        return ctx


def _save_attachments(ticket: Ticket, user, files) -> list[Attachment]:
    return [
        Attachment.objects.create(
            ticket=ticket, uploaded_by=user, file=f, original_name=f.name, size=f.size
        )
        for f in files
    ]


class TicketCreateView(LoginRequiredMixin, CreateView):
    model = Ticket
    form_class = TicketCreateForm
    template_name = "tickets/ticket_form.html"

    def form_valid(self, form):
        form.instance.created_by = self.request.user
        with transaction.atomic():
            response = super().form_valid(form)
            ticket: Ticket = form.instance
            saved = _save_attachments(ticket, self.request.user, form.cleaned_data["attachments"])
        text = f"Đã tạo ticket {ticket.short_id}"
        if saved:
            text += f" kèm {len(saved)} tệp đính kèm"
        messages.success(self.request, text + ".")
        return response

    def get_success_url(self):
        ticket = cast(Ticket, self.object)
        return reverse_lazy("tickets:detail", kwargs={"pk": ticket.pk})


class TicketUpdateView(LoginRequiredMixin, TicketQuerysetMixin, UpdateView):
    model = Ticket
    form_class = TicketForm
    template_name = "tickets/ticket_form.html"

    def get_success_url(self):
        messages.success(self.request, "Đã cập nhật thông tin ticket.")
        ticket = cast(Ticket, self.object)
        return reverse_lazy("tickets:detail", kwargs={"pk": ticket.pk})


def _get_accessible_ticket(request: HttpRequest, pk) -> Ticket:
    qs = Ticket.objects.select_related("category", "assignee", "created_by")
    user = request.user
    if isinstance(user, User) and user.role == User.Role.CUSTOMER:
        qs = qs.filter(created_by=user)
    ticket = qs.filter(pk=pk).first()
    if not ticket:
        raise Http404("Không tìm thấy ticket.")
    return ticket


@login_required
@require_POST
def ticket_upload_view(request: HttpRequest, pk) -> HttpResponse:
    ticket = _get_accessible_ticket(request, pk)
    if ticket.status == Ticket.Status.CLOSED:
        messages.error(request, "Ticket đã đóng, không thể tải tệp đính kèm.")
        return redirect("tickets:detail", pk=pk)
    form = AttachmentUploadForm(request.POST, request.FILES)
    if form.is_valid():
        saved = _save_attachments(ticket, request.user, form.cleaned_data["attachments"])
        messages.success(request, f"Đã tải lên {len(saved)} tệp.")
    else:
        for error in form.errors.get("attachments", []):
            messages.error(request, str(error))
    return redirect(f"{reverse('tickets:detail', kwargs={'pk': pk})}#tab-attachments")


@login_required
def attachment_download_view(request: HttpRequest, pk) -> FileResponse:
    qs = Attachment.objects.select_related("ticket")
    user = request.user
    if isinstance(user, User) and user.role == User.Role.CUSTOMER:
        qs = qs.filter(ticket__created_by=user)
    attachment = qs.filter(pk=pk).first()
    if not attachment or not attachment.file:
        raise Http404("Không tìm thấy tệp.")
    try:
        handle = attachment.file.open("rb")
    except FileNotFoundError as exc:
        raise Http404("Tệp không còn trên máy chủ.") from exc
    return FileResponse(handle, as_attachment=True, filename=attachment.original_name)


@login_required
@require_POST
def ticket_assign_view(request: HttpRequest, pk) -> HttpResponse:
    user = cast(User, request.user)
    if user.role != User.Role.MANAGER:
        messages.error(request, "Chỉ Quản lý mới có quyền gán người xử lý.")
        return redirect("tickets:detail", pk=pk)

    ticket = _get_accessible_ticket(request, pk)
    agent_id = request.POST.get("agent_id")
    agent = get_object_or_404(User, pk=agent_id, role=User.Role.AGENT)
    try:
        assign_ticket(ticket=ticket, agent=agent, actor=user)
        messages.success(request, f"Đã gán ticket cho nhân viên {agent.username}.")
    except TicketServiceError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def ticket_status_view(request: HttpRequest, pk) -> HttpResponse:
    user = cast(User, request.user)
    if user.role == User.Role.CUSTOMER:
        messages.error(request, "Khách hàng không được tự đổi trạng thái xử lý.")
        return redirect("tickets:detail", pk=pk)

    ticket = _get_accessible_ticket(request, pk)
    new_status = request.POST.get("status", "")
    try:
        change_ticket_status(ticket=ticket, new_status=new_status, actor=user)
        messages.success(request, f"Đã chuyển trạng thái sang {ticket.get_status_display()}.")
    except TicketServiceError as exc:
        messages.error(request, str(exc))
    return redirect("tickets:detail", pk=pk)


@login_required
@require_POST
def ticket_comment_view(request: HttpRequest, pk) -> HttpResponse:
    user = cast(User, request.user)
    ticket = _get_accessible_ticket(request, pk)
    form = CommentForm(request.POST)
    if form.is_valid():
        try:
            add_comment(
                ticket=ticket,
                author=user,
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
    user = request.user
    return (
        isinstance(user, User)
        and user.is_authenticated
        and (user.role == User.Role.MANAGER or user.is_staff)
    )


def _count_tickets_by(field: str) -> Coalesce:
    counts = (
        Ticket.objects.filter(**{field: OuterRef("pk")})
        .order_by()
        .values(field)
        .annotate(n=Count("id"))
        .values("n")
    )
    return Coalesce(Subquery(counts, output_field=IntegerField()), 0)


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
        created_count=_count_tickets_by("created_by"),
        assigned_count=_count_tickets_by("assignee"),
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
def manage_stats_view(request: HttpRequest) -> HttpResponse:
    if not _check_manager(request):
        messages.error(request, "Chỉ Quản lý hoặc Admin mới có quyền xem thống kê.")
        return redirect("tickets:list")

    context = {**selectors.dashboard_stats(), "sla_hours": selectors.SLA_HOURS}
    return render(request, "tickets/manage_stats.html", context)


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
