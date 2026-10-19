"""Admin site."""

from django import forms as django_forms
from django.contrib import admin, messages

from wanderer.models import (
    AstropathACL,
    AstropathACLMapping,
    AstropathConfiguration,
    MapStructure,
    Structure,
    StructureFilterPreset,
    StructureHistory,
    WandererAccount,
    WandererManagedMap,
)
from wanderer.tasks import sync_all_astropath_acls, sync_astropath_acl
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


@admin.register(AstropathConfiguration)
class AstropathConfigurationAdmin(admin.ModelAdmin):
    list_display = ["url"]
    actions = ["sync_all_acls", "test_connection"]

    def has_add_permission(self, request):
        return not AstropathConfiguration.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.action(description="Sync all Astropath ACL mappings now")
    def sync_all_acls(self, request, queryset):
        sync_all_astropath_acls.delay()
        self.message_user(
            request,
            "Queued sync for all Astropath ACLs. Check the worker log for results.",
            messages.SUCCESS,
        )

    @admin.action(description="Test connection and list available ACLs")
    def test_connection(self, request, queryset):
        from wanderer.astropath import AstropathNotConfiguredError, list_acls
        try:
            acls = list_acls()
        except AstropathNotConfiguredError as e:
            self.message_user(request, str(e), messages.ERROR)
            return
        except Exception as e:
            self.message_user(request, f"Astropath API error: {e}", messages.ERROR)
            return
        if not acls:
            self.message_user(
                request,
                "Connected successfully, but no ACLs are visible to this API key. "
                "Create ACLs in the Astropath UI and ensure this key has access to them.",
                messages.WARNING,
            )
        else:
            names = ", ".join(f"{a['name']} (ID: {a['id']})" for a in acls)
            self.message_user(request, f"Connected. {len(acls)} ACL(s) available: {names}", messages.SUCCESS)


class AstropathACLMappingInline(admin.TabularInline):
    model = AstropathACLMapping
    extra = 1
    fields = ["group", "role"]


@admin.register(AstropathACL)
class AstropathACLAdmin(admin.ModelAdmin):
    list_display = ["acl_id", "name", "group_summary"]
    inlines = [AstropathACLMappingInline]
    actions = ["trigger_sync"]

    def group_summary(self, obj):
        parts = [f"{m.group.name} ({m.role})" for m in obj.mappings.select_related("group").all()]
        return ", ".join(parts) or "—"
    group_summary.short_description = "Groups"

    def formfield_for_dbfield(self, db_field, request, **kwargs):
        if db_field.name == "acl_id":
            from wanderer.astropath import AstropathNotConfiguredError, list_acls
            try:
                acls = list_acls()
            except AstropathNotConfiguredError:
                return super().formfield_for_dbfield(db_field, request, **kwargs)
            except Exception as e:
                messages.error(request, f"Could not fetch ACL list from Astropath: {e}")
                return super().formfield_for_dbfield(db_field, request, **kwargs)

            if not acls:
                messages.warning(
                    request,
                    "Connected to Astropath but no ACLs are visible to this API key. "
                    "Create ACLs in the Astropath UI and ensure the key has access to them.",
                )
                return super().formfield_for_dbfield(db_field, request, **kwargs)

            choices = [(acl["id"], f"{acl['name']} (ID: {acl['id']})") for acl in acls]
            return django_forms.TypedChoiceField(
                choices=choices,
                coerce=int,
                label="ACL",
                help_text="Select the Astropath ACL to map groups into.",
            )
        return super().formfield_for_dbfield(db_field, request, **kwargs)

    def save_model(self, request, obj, form, change):
        if not obj.name:
            from wanderer.astropath import list_acls
            try:
                acls = list_acls()
                match = next((a for a in acls if a["id"] == obj.acl_id), None)
                if match:
                    obj.name = match["name"]
            except Exception:
                pass
        super().save_model(request, obj, form, change)

    @admin.action(description="Sync selected ACLs to Astropath now")
    def trigger_sync(self, request, queryset):
        acl_ids = list(queryset.values_list("acl_id", flat=True))
        for acl_id in acl_ids:
            sync_astropath_acl.delay(acl_id)
        self.message_user(
            request,
            f"Queued sync for {len(acl_ids)} Astropath ACL(s). Check the worker log for results.",
            messages.SUCCESS,
        )


@admin.register(WandererAccount)
class WandererUserAdmin(admin.ModelAdmin):
    list_filter = ["wanderer_map"]
    list_display = ["user", "wanderer_map"]
    readonly_fields = ["user", "wanderer_map"]

    def has_add_permission(self, request):
        return False
