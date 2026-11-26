from django import forms

from .models import Comment, Ticket
from .validators import ALLOWED_EXTENSIONS, MAX_FILES_PER_UPLOAD, validate_attachment

ACCEPT_ATTR = ",".join(f".{ext}" for ext in ALLOWED_EXTENSIONS)


class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleFileField(forms.FileField):
    def __init__(self, *args, **kwargs):
        kwargs.setdefault("widget", MultipleFileInput(attrs={"accept": ACCEPT_ATTR}))
        kwargs.setdefault("required", False)
        super().__init__(*args, **kwargs)

    def clean(self, data, initial=None):
        files = [f for f in (data if isinstance(data, list | tuple) else [data]) if f]
        if len(files) > MAX_FILES_PER_UPLOAD:
            raise forms.ValidationError(f"Chỉ đính kèm tối đa {MAX_FILES_PER_UPLOAD} tệp mỗi lần.")
        errors = []
        cleaned = []
        for f in files:
            f = super().clean(f, initial)
            try:
                validate_attachment(f)
            except forms.ValidationError as exc:
                errors.extend(exc.messages)
            cleaned.append(f)
        if errors:
            raise forms.ValidationError(errors)
        return cleaned


class TicketForm(forms.ModelForm):
    class Meta:
        model = Ticket
        fields = ["title", "category", "priority", "description"]
        widgets = {
            "title": forms.TextInput(
                attrs={
                    "class": "mv-input",
                    "placeholder": "Nhập tiêu đề sự cố (tối thiểu 5 ký tự)...",
                }
            ),
            "category": forms.Select(attrs={"class": "mv-select"}),
            "priority": forms.Select(attrs={"class": "mv-select"}),
            "description": forms.Textarea(
                attrs={
                    "class": "mv-textarea",
                    "rows": 5,
                    "placeholder": "Mô tả chi tiết hiện tượng lỗi, các bước tái hiện...",
                }
            ),
        }

    def clean_title(self) -> str:
        title = (self.cleaned_data.get("title") or "").strip()
        if len(title) < 5:
            raise forms.ValidationError("Tiêu đề tối thiểu 5 ký tự.")
        return title


class TicketCreateForm(TicketForm):
    attachments = MultipleFileField(label="Tệp đính kèm")


class AttachmentUploadForm(forms.Form):
    attachments = MultipleFileField(label="Tệp đính kèm", required=True)


class CommentForm(forms.ModelForm):
    class Meta:
        model = Comment
        fields = ["content", "is_internal"]
        widgets = {
            "content": forms.Textarea(
                attrs={
                    "class": "mv-textarea",
                    "rows": 3,
                    "placeholder": "Nhập bình luận hoặc phản hồi xử lý của bạn...",
                }
            ),
            "is_internal": forms.CheckboxInput(attrs={"class": "mv-toggle-input"}),
        }
