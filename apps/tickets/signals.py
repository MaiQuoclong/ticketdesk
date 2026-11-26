from django.db import transaction
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from apps.accounts.models import User

from . import selectors
from .models import Category, Ticket


@receiver(post_save, sender=Ticket)
@receiver(post_delete, sender=Ticket)
@receiver(post_save, sender=Category)
@receiver(post_delete, sender=Category)
@receiver(post_save, sender=User)
@receiver(post_delete, sender=User)
def clear_stats_cache(sender, **kwargs) -> None:
    """Xoá cache thống kê sau khi ticket, danh mục hoặc người dùng thay đổi và đã commit."""
    if kwargs.get("update_fields") == frozenset({"last_login"}):
        return
    transaction.on_commit(selectors.invalidate_stats)
