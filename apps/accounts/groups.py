MANAGER_GROUP = "Quản lý"

MANAGER_PERMISSIONS = {
    "tickets": {
        "ticket": ["add", "change", "delete", "view"],
        "category": ["add", "change", "delete", "view"],
        "comment": ["add", "change", "delete", "view"],
        "attachment": ["view"],
        "tickethistory": ["view"],
    },
}


def permission_codenames():
    for app_label, models in MANAGER_PERMISSIONS.items():
        for model, actions in models.items():
            for action in actions:
                yield app_label, f"{action}_{model}"
