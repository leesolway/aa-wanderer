"""Views."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _

from allianceauth.services.hooks import get_extension_logger

from wanderer.models import MapStructure, WandererAccount, WandererManagedMap
from wanderer.tasks import add_alts_to_map, sync_all_map_structures

logger = get_extension_logger(__name__)


@login_required
@permission_required("wanderer.basic_access")
def structures(request):
    """Display synced map structures with optional filtering."""
    solar_systems = [v for v in request.GET.getlist("solar_system") if v.strip()]
    corporations = [v for v in request.GET.getlist("corporation") if v.strip()]
    alliances = [v for v in request.GET.getlist("alliance") if v.strip()]

    qs = MapStructure.objects.select_related("map").filter(map__sync_structures=True)

    if solar_systems:
        qs = qs.filter(solar_system_name__in=solar_systems)
    if corporations:
        q = Q()
        for c in corporations:
            q |= Q(owner_name=c)
        qs = qs.filter(q)
    if alliances:
        qs = qs.filter(alliance_name__in=alliances)

    return render(
        request,
        "wanderer/structures.html",
        {
            "structures": qs,
            "solar_systems": solar_systems,
            "corporations": corporations,
            "alliances": alliances,
            "active_filters": bool(solar_systems or corporations or alliances),
        },
    )


@login_required
@permission_required("wanderer.basic_access")
def autocomplete_solar_systems(request):
    q = request.GET.get("q", "").strip()
    qs = MapStructure.objects.all()
    if q:
        qs = qs.filter(solar_system_name__icontains=q)
    values = list(
        qs.values_list("solar_system_name", flat=True)
        .distinct()
        .order_by("solar_system_name")[:20]
    )
    return JsonResponse({"results": [{"value": v, "text": v} for v in values]})


@login_required
@permission_required("wanderer.basic_access")
def autocomplete_corporations(request):
    q = request.GET.get("q", "").strip()
    qs = MapStructure.objects.exclude(owner_name="")
    if q:
        qs = qs.filter(Q(owner_name__icontains=q) | Q(owner_ticker__icontains=q))
    rows = (
        qs.values("owner_name", "owner_ticker")
        .distinct()
        .order_by("owner_name")[:20]
    )
    results = [
        {"value": r["owner_name"], "text": f"{r['owner_name']} [{r['owner_ticker']}]" if r["owner_ticker"] else r["owner_name"]}
        for r in rows
    ]
    return JsonResponse({"results": results})


@login_required
@permission_required("wanderer.basic_access")
def autocomplete_alliances(request):
    q = request.GET.get("q", "").strip()
    qs = MapStructure.objects.exclude(alliance_name="")
    if q:
        qs = qs.filter(Q(alliance_name__icontains=q) | Q(alliance_ticker__icontains=q))
    rows = (
        qs.values("alliance_name", "alliance_ticker")
        .distinct()
        .order_by("alliance_name")[:20]
    )
    results = [
        {"value": r["alliance_name"], "text": f"{r['alliance_name']} [{r['alliance_ticker']}]" if r["alliance_ticker"] else r["alliance_name"]}
        for r in rows
    ]
    return JsonResponse({"results": results})


@login_required
@permission_required("wanderer.basic_access")
def force_sync_structures(request):
    """Manually trigger a structure sync for all maps."""
    if not request.user.is_staff:
        messages.error(request, _("You do not have permission to do that."))
        return redirect("wanderer:structures")
    sync_all_map_structures.delay()
    messages.success(request, _("Structure sync queued."))
    return redirect("wanderer:structures")


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
