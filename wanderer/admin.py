"""Admin site."""

from django.contrib import admin

from wanderer.models import (
    MapStructure,
    Structure,
    StructureFilterPreset,
    StructureHistory,
    WandererAccount,
    WandererManagedMap,
)
from wanderer.wanderer import create_acl_associated_to_map


class ReadOnlyAdminMixin:
    """Admin mixin for models whose data is entirely managed by wanderer's sync/
    reconciliation tasks and must only ever be viewed, never hand-edited or added."""

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False


@admin.register(WandererManagedMap)
class WandererManagedMapAdmin(admin.ModelAdmin):
    list_display = ["name", "wanderer_url", "map_slug", "sync_structures"]
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
        ("Sync", {"fields": ["sync_structures"]}),
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


@admin.register(MapStructure)
class MapStructureAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["name", "structure_type", "solar_system", "owner_name", "owner_ticker", "alliance_name", "status", "inserted_at", "map", "last_synced"]
    list_filter = ["map", "status", "structure_type"]
    search_fields = ["name", "solar_system__name", "owner_name", "owner_ticker"]
    readonly_fields = [f.name for f in MapStructure._meta.get_fields() if hasattr(f, "name")]


class StructureHistoryInline(admin.TabularInline):
    model = StructureHistory
    extra = 0
    can_delete = False
    fields = ["recorded_at", "change_type", "changed_fields", "owner_name", "alliance_name", "status"]
    readonly_fields = fields
    ordering = ["-recorded_at"]

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Structure)
class StructureAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["name", "structure_type", "solar_system", "owner_name", "owner_ticker", "alliance_name", "status", "is_active", "last_seen_at", "removed_at", "last_source_map"]
    list_filter = ["is_active", "status", "structure_type"]
    search_fields = ["name", "solar_system__name", "owner_name", "owner_ticker"]
    # .fields (not get_fields()) - the latter also returns the reverse "history"
    # relation from StructureHistory, which isn't a real renderable field here.
    readonly_fields = [f.name for f in Structure._meta.fields]
    inlines = [StructureHistoryInline]


@admin.register(StructureHistory)
class StructureHistoryAdmin(ReadOnlyAdminMixin, admin.ModelAdmin):
    list_display = ["structure", "change_type", "recorded_at", "owner_name", "alliance_name"]
    list_filter = ["change_type"]
    search_fields = ["structure__name", "owner_name", "alliance_name"]
    readonly_fields = [f.name for f in StructureHistory._meta.fields]


@admin.register(StructureFilterPreset)
class StructureFilterPresetAdmin(admin.ModelAdmin):
    list_display = ["priority", "name", "filter_mode", "created_by", "created_at"]
    list_display_links = ["name"]
    list_editable = ["priority"]
    list_filter = ["filter_mode"]
    search_fields = ["name"]
    ordering = ["priority", "name"]
    readonly_fields = ["created_by", "created_at"]

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(WandererAccount)
class WandererUserAdmin(admin.ModelAdmin):
    list_filter = ["wanderer_map"]
    list_display = ["user", "wanderer_map"]
    readonly_fields = ["user", "wanderer_map"]

    def has_add_permission(self, request):
        return False
