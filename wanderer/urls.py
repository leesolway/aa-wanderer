"""Routes."""

from django.urls import include, path

from . import views

app_name = "wanderer"

module_urls = [
    path("link/<int:map_id>", views.link, name="link"),
    path("sync/<int:map_id>", views.sync, name="sync"),
    path("remove/<int:map_id>", views.remove, name="remove"),
]

urlpatterns = [path("wanderer/", include((module_urls, app_name), namespace=app_name))]
