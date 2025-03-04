"""Views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.shortcuts import get_object_or_404, redirect
from django.utils.translation import gettext_lazy as _

from allianceauth.services.hooks import get_extension_logger

from wanderer.models import WandererAccount, WandererManagedMap
from wanderer.tasks import add_alts_to_map

logger = get_extension_logger(__name__)


@login_required
@permission_required("wanderer.basic_access")
def link(request, map_id: int):
    """Link a new user to a wanderer map"""
    wanderer_map = get_object_or_404(WandererManagedMap, pk=map_id)
    user = request.user

    if not wanderer_map.accessible_by(user):
        messages.warning(request, _("You don't have the access for this map"))
        logger.warning(
            "User id %d tried to access map id %d without authorization",
            user.id,
            wanderer_map.id,
        )

    elif wanderer_map.user_has_account(user):
        messages.warning(request, _("You are already linked to this map"))
    else:
        wanderer_user = WandererAccount.objects.create(
            user=user, wanderer_map=wanderer_map
        )
        add_alts_to_map.delay(wanderer_user.id, wanderer_map.id)
        messages.success(
            request,
            _(
                "Successfully linked your account to this map. Character update starting now."
            ),
        )

    return redirect("services:services")


@login_required
@permission_required("wanderer.basic_access")
def sync(request, map_id: int):
    """Checks that all the user characters are properly added to the access list"""
    wanderer_map = get_object_or_404(WandererManagedMap, pk=map_id)
    wanderer_user = get_object_or_404(
        WandererAccount, user=request.user, wanderer_map=wanderer_map
    )
    add_alts_to_map.delay(wanderer_user.id, wanderer_map.id)
    messages.success(request, _("Updating your characters with the map."))

    return redirect("services:services")


@login_required
@permission_required("wanderer.basic_access")
def remove(request, map_id: int):
    """Removes all characters from the map access list and deletes the user"""
    wanderer_map = get_object_or_404(WandererManagedMap, pk=map_id)
    user = request.user

    if not wanderer_map.user_has_account(user):
        messages.warning(request, _("You don't seem to be linked to this map."))
    else:
        wanderer_map.delete_user(user)

        messages.success(
            request, _("Successfully removed you from the map %s") % wanderer_map
        )

    return redirect("services:services")
