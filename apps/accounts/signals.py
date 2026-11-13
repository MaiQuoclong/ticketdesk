from django.contrib.auth.models import Group
from django.db.models.signals import post_save
from django.dispatch import receiver

from .groups import MANAGER_GROUP
from .models import User


@receiver(post_save, sender=User)
def sync_manager_group(sender, instance: User, raw: bool = False, **kwargs):
    if raw:
        return
    group = Group.objects.filter(name=MANAGER_GROUP).first()
    if group is None:
        return
    if instance.role == User.Role.MANAGER:
        instance.groups.add(group)
    else:
        instance.groups.remove(group)
