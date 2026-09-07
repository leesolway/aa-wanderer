"""Routes."""

from django.urls import path

from . import views

app_name = "wanderer"

urlpatterns = [
    path("structures/", views.structures, name="structures"),
    path("structures/force-sync/", views.force_sync_structures, name="force_sync_structures"),
    path("structures/presets/save/", views.preset_save, name="preset_save"),
    path("structures/presets/<int:preset_id>/delete/", views.preset_delete, name="preset_delete"),
    path("autocomplete/solar-systems/", views.autocomplete_solar_systems, name="autocomplete_solar_systems"),
    path("autocomplete/corporations/", views.autocomplete_corporations, name="autocomplete_corporations"),
    path("autocomplete/alliances/", views.autocomplete_alliances, name="autocomplete_alliances"),
    path("link/<int:map_id>", views.link, name="link"),
    path("sync/<int:map_id>", views.sync, name="sync"),
    path("remove/<int:map_id>", views.remove, name="remove"),
]
