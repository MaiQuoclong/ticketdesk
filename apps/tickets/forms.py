from django import forms

from .models import Comment, Ticket


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
