"""Views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from wanderer.models import WandererManagedMap, WandererUser


@login_required
@permission_required("wanderer.basic_access")
def index(request):
    """Render index view."""
    context = {"text": "Hello, World!"}
    return render(request, "wanderer/index.html", context)


@login_required
@permission_required("wanderer.basic_access")
def link(request, map_id: int):
    """Link a new user to a wanderer map"""
    # FIXME check if the user is allowed to join this map!!
    wanderer_map = get_object_or_404(WandererManagedMap, pk=map_id)
    user = request.user

    if wanderer_map.user_has_account(user):
        messages.warning(request, _("You are already linked to this map"))
    else:
        WandererUser.objects.create(user=user, wanderer_map=wanderer_map)
        messages.success(
            request,
            _(
                "Successfully linked your account to this map. Character update starting now."
            ),
        )
        # TODO add update

    return redirect("services:services")


@login_required
@permission_required("wanderer.basic_access")
def sync(request, map_id: int):
    """Checks that all the user characters are properly added to the access list"""
    # TODO create sync code


@login_required
@permission_required("wanderer.basic_access")
def remove(request, map_id: int):
    """Removes all characters from the map access list and deletes the user"""
    # TODO create remove code
    pass
