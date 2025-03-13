"""Routes."""

from django.urls import path

from . import views

app_name = "wanderer"

urlpatterns = [
    path("link/<int:map_id>", views.link, name="link"),
    path("sync/<int:map_id>", views.sync, name="sync"),
    path("remove/<int:map_id>", views.remove, name="remove"),
]
