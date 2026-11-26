import pytest
from django.core.files.uploadedfile import SimpleUploadedFile
from django.urls import reverse

from apps.tickets.models import Attachment, Ticket
from apps.tickets.validators import MAX_FILE_SIZE

from .factories import (
    AgentFactory,
    AttachmentFactory,
    CategoryFactory,
    CommentFactory,
    CustomerFactory,
    ManagerFactory,
    TicketFactory,
)

pytestmark = pytest.mark.django_db

CREATE = reverse("tickets:create")


@pytest.fixture(autouse=True)
def _media_tmp(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path


def _png(name="anh.png", size=16):
    return SimpleUploadedFile(name, b"\x89PNG" + b"0" * (size - 4), content_type="image/png")


def _payload(category, **extra):
    return {
        "title": "Máy tính không lên nguồn",
        "category": category.pk,
        "priority": 2,
        "description": "Bấm nút nguồn không có phản hồi.",
        **extra,
    }


def test_form_tao_co_vung_keo_tha_va_multipart(client):
    client.force_login(CustomerFactory())
    html = client.get(CREATE).content.decode()
    assert 'enctype="multipart/form-data"' in html
    assert "data-dropzone" in html
    assert 'name="attachments"' in html
    assert "multiple" in html
    assert "js/attachments.js" in html


def test_tao_ticket_khong_tep(client):
    user = CustomerFactory()
    client.force_login(user)
    resp = client.post(CREATE, _payload(CategoryFactory()))
    ticket = Ticket.objects.get(created_by=user)
    assert resp.status_code == 302
    assert resp.url == reverse("tickets:detail", args=[ticket.pk])
    assert ticket.attachments.count() == 0


def test_tao_ticket_kem_nhieu_tep(client):
    user = CustomerFactory()
    client.force_login(user)
    files = [_png("a.png"), SimpleUploadedFile("b.pdf", b"%PDF-1.4", "application/pdf")]
    resp = client.post(CREATE, _payload(CategoryFactory(), attachments=files), follow=True)
    ticket = Ticket.objects.get(created_by=user)
    names = sorted(ticket.attachments.values_list("original_name", flat=True))
    assert names == ["a.png", "b.pdf"]
    assert all(a.uploaded_by == user for a in ticket.attachments.all())
    assert "kèm 2 tệp đính kèm" in resp.content.decode()


def test_tep_sai_dinh_dang_bi_tu_choi_va_khong_tao_ticket(client):
    client.force_login(CustomerFactory())
    bad = SimpleUploadedFile("virus.exe", b"MZ", "application/octet-stream")
    resp = client.post(CREATE, _payload(CategoryFactory(), attachments=[bad]))
    assert resp.status_code == 200
    assert "sai định dạng" in resp.content.decode()
    assert Ticket.objects.count() == 0


def test_tep_qua_5mb_bi_tu_choi(client):
    client.force_login(CustomerFactory())
    big = _png("lon.png", MAX_FILE_SIZE + 1)
    resp = client.post(CREATE, _payload(CategoryFactory(), attachments=[big]))
    assert "vượt quá 5 MB" in resp.content.decode()
    assert Ticket.objects.count() == 0


def test_qua_5_tep_bi_tu_choi(client):
    client.force_login(CustomerFactory())
    files = [_png(f"{i}.png") for i in range(6)]
    resp = client.post(CREATE, _payload(CategoryFactory(), attachments=files))
    assert "tối đa 5 tệp" in resp.content.decode()
    assert Ticket.objects.count() == 0


def test_form_sua_khong_co_vung_dinh_kem(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory())
    client.force_login(user)
    html = client.get(reverse("tickets:edit", args=[ticket.pk])).content.decode()
    assert "data-dropzone" not in html
    assert "js/attachments.js" not in html


def test_chi_tiet_co_3_tab(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory())
    AttachmentFactory(ticket=ticket, original_name="log.png")
    client.force_login(user)
    html = client.get(reverse("tickets:detail", args=[ticket.pk])).content.decode()
    for tab in ["tab-comments", "tab-attachments", "tab-history"]:
        assert f'id="{tab}"' in html
    assert "Đính kèm (1)" in html
    assert "log.png" in html


def test_khach_khong_thay_ghi_chu_noi_bo_va_khoi_thao_tac(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory())
    CommentFactory(ticket=ticket, content="Ghi chú bí mật", is_internal=True)
    CommentFactory(ticket=ticket, content="Trả lời công khai", is_internal=False)
    client.force_login(user)
    html = client.get(reverse("tickets:detail", args=[ticket.pk])).content.decode()
    assert "Ghi chú bí mật" not in html
    assert "Trả lời công khai" in html
    assert "Phân công xử lý" not in html
    assert "Cập nhật trạng thái" not in html
    assert "Ghi chú nội bộ</strong>" not in html


def test_agent_thay_doi_trang_thai_nhung_khong_thay_gan(client):
    ticket = TicketFactory(category=CategoryFactory())
    client.force_login(AgentFactory())
    html = client.get(reverse("tickets:detail", args=[ticket.pk])).content.decode()
    assert "Cập nhật trạng thái" in html
    assert "Phân công xử lý" not in html
    assert "Ghi chú nội bộ</strong>" in html


def test_manager_thay_ca_hai_khoi_thao_tac(client):
    ticket = TicketFactory(category=CategoryFactory())
    client.force_login(ManagerFactory())
    html = client.get(reverse("tickets:detail", args=[ticket.pk])).content.decode()
    assert "Phân công xử lý" in html
    assert "Cập nhật trạng thái" in html


def test_ticket_dong_an_form_binh_luan_va_tai_tep(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory(), status="closed")
    client.force_login(user)
    html = client.get(reverse("tickets:detail", args=[ticket.pk])).content.decode()
    assert "Ticket đã đóng, không thể bình luận thêm." in html
    assert reverse("tickets:upload", args=[ticket.pk]) not in html


def test_tai_tep_tu_trang_chi_tiet(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory())
    client.force_login(user)
    resp = client.post(
        reverse("tickets:upload", args=[ticket.pk]), {"attachments": [_png("x.png")]}
    )
    assert resp.status_code == 302
    assert resp.url.endswith("#tab-attachments")
    assert ticket.attachments.get().original_name == "x.png"


def test_tai_tep_sai_bao_loi(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory())
    client.force_login(user)
    bad = SimpleUploadedFile("a.txt", b"hi", "text/plain")
    resp = client.post(
        reverse("tickets:upload", args=[ticket.pk]), {"attachments": [bad]}, follow=True
    )
    assert "sai định dạng" in resp.content.decode()
    assert ticket.attachments.count() == 0


def test_tai_tep_khong_chon_tep_bao_loi(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory())
    client.force_login(user)
    resp = client.post(reverse("tickets:upload", args=[ticket.pk]), {}, follow=True)
    assert resp.status_code == 200
    assert ticket.attachments.count() == 0


def test_tai_tep_vao_ticket_dong_bi_chan(client):
    user = CustomerFactory()
    ticket = TicketFactory(created_by=user, category=CategoryFactory(), status="closed")
    client.force_login(user)
    resp = client.post(
        reverse("tickets:upload", args=[ticket.pk]), {"attachments": [_png()]}, follow=True
    )
    assert "Ticket đã đóng" in resp.content.decode()
    assert ticket.attachments.count() == 0


def test_khach_khong_tai_tep_vao_ticket_nguoi_khac(client):
    ticket = TicketFactory(category=CategoryFactory())
    client.force_login(CustomerFactory())
    resp = client.post(reverse("tickets:upload", args=[ticket.pk]), {"attachments": [_png()]})
    assert resp.status_code == 404


def test_tai_xuong_tep_dung_ten_goc(client):
    user = CustomerFactory()
    att = AttachmentFactory(ticket=TicketFactory(created_by=user, category=CategoryFactory()))
    client.force_login(user)
    resp = client.get(reverse("tickets:attachment_download", args=[att.pk]))
    assert resp.status_code == 200
    assert att.original_name in resp["Content-Disposition"]
    assert b"".join(resp.streaming_content).startswith(b"\x89PNG")


def test_khach_khac_khong_tai_duoc_tep(client):
    att = AttachmentFactory(ticket=TicketFactory(category=CategoryFactory()))
    client.force_login(CustomerFactory())
    resp = client.get(reverse("tickets:attachment_download", args=[att.pk]))
    assert resp.status_code == 404


def test_agent_tai_duoc_tep_moi_ticket(client):
    att = AttachmentFactory(ticket=TicketFactory(category=CategoryFactory()))
    client.force_login(AgentFactory())
    resp = client.get(reverse("tickets:attachment_download", args=[att.pk]))
    assert resp.status_code == 200


def test_tep_mat_tren_dia_tra_404(client):
    att = AttachmentFactory(ticket=TicketFactory(category=CategoryFactory()))
    att.file.storage.delete(att.file.name)
    client.force_login(ManagerFactory())
    resp = client.get(reverse("tickets:attachment_download", args=[att.pk]))
    assert resp.status_code == 404


def test_chua_dang_nhap_khong_tai_duoc_tep(client):
    att = AttachmentFactory(ticket=TicketFactory(category=CategoryFactory()))
    resp = client.get(reverse("tickets:attachment_download", args=[att.pk]))
    assert resp.status_code == 302
    assert Attachment.objects.count() == 1
