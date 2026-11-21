from django.contrib.auth.models import Group, Permission
from django.db.models.signals import post_migrate, post_save
from django.dispatch import receiver

from .groups import MANAGER_GROUP, permission_codenames
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


@receiver(post_migrate)
def ensure_manager_group(sender, using: str = "default", **kwargs):
    group, _ = Group.objects.using(using).get_or_create(name=MANAGER_GROUP)
    perms = Permission.objects.using(using).none()
    for app_label, codename in permission_codenames():
        perms |= Permission.objects.using(using).filter(
            content_type__app_label=app_label, codename=codename
        )
    group.permissions.add(*perms)
    for user in User.objects.using(using).filter(role=User.Role.MANAGER):
        user.groups.add(group)
