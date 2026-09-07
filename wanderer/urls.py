"""Routes."""

from django.urls import path

from . import views

app_name = "wanderer"

urlpatterns = [
    path("structures/", views.structures, name="structures"),
    path("structures/force-sync/", views.force_sync_structures, name="force_sync_structures"),
    path("link/<int:map_id>", views.link, name="link"),
    path("sync/<int:map_id>", views.sync, name="sync"),
    path("remove/<int:map_id>", views.remove, name="remove"),
]
