"""Admin site."""

from django.contrib import admin

from wanderer.models import WandererAccount, WandererManagedMap
from wanderer.wanderer import create_acl_associated_to_map


@admin.register(WandererManagedMap)
class WandererManagedMapAdmin(admin.ModelAdmin):
    readonly_fields = ["map_acl_id", "map_acl_api_key"]
    fieldsets = [
        (None, {"fields": ["name", "wanderer_url", "map_slug", "map_api_key"]}),
        ("Access List", {"fields": ["map_acl_id", "map_acl_api_key"]}),
        (
            "Access",
            {
                "fields": [
                    "state_access",
                    "group_access",
                    "character_access",
                    "corporation_access",
                    "alliance_access",
                ]
            },
        ),
    ]

    def save_model(self, request, obj, form, change):
        if not change:  # Only on item creation
            character = request.user.profile.main_character
            w = form.save(commit=False)
            map_acl_id, map_acl_api_key = create_acl_associated_to_map(
                w.wanderer_url, w.map_slug, character.character_id, w.map_api_key
            )
            w.map_acl_id = map_acl_id
            w.map_acl_api_key = map_acl_api_key
            w.save()
        else:
            super().save_model(request, obj, form, change)


@admin.register(WandererAccount)
class WandererUserAdmin(admin.ModelAdmin):
    list_filter = ["wanderer_map"]
    list_display = ["user", "wanderer_map"]
    readonly_fields = ["user", "wanderer_map"]

    def has_add_permission(self, request):
        return False
