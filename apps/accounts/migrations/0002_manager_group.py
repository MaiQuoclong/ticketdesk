from django.contrib.auth.management import create_permissions
from django.db import migrations

from apps.accounts.groups import MANAGER_GROUP, permission_codenames


def create_manager_group(apps, schema_editor):
    for app_config in apps.get_app_configs():
        app_config.models_module = True
        create_permissions(app_config, verbosity=0)
        app_config.models_module = None

    Group = apps.get_model("auth", "Group")
    Permission = apps.get_model("auth", "Permission")
    User = apps.get_model("accounts", "User")

    group, _ = Group.objects.get_or_create(name=MANAGER_GROUP)
    perms = [
        Permission.objects.get(content_type__app_label=app_label, codename=codename)
        for app_label, codename in permission_codenames()
    ]
    group.permissions.set(perms)
    for user in User.objects.filter(role="manager"):
        user.groups.add(group)


def remove_manager_group(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    Group.objects.filter(name=MANAGER_GROUP).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0001_initial"),
        ("auth", "0012_alter_user_first_name_max_length"),
        ("contenttypes", "0002_remove_content_type_name"),
        ("tickets", "0003_backfill_resolved_at"),
    ]

    operations = [
        migrations.RunPython(create_manager_group, remove_manager_group),
    ]
