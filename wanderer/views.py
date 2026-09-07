"""Views."""

import json

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from eve_sde.models import SolarSystem

from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo
from allianceauth.services.hooks import get_extension_logger

from wanderer.models import MapStructure, StructureFilterPreset, WandererAccount, WandererManagedMap
from wanderer.tasks import add_alts_to_map, sync_all_map_structures

logger = get_extension_logger(__name__)


@login_required
@permission_required("wanderer.basic_access")
def structures(request):
    """Display synced map structures with optional filtering."""
    system_ids = [v for v in request.GET.getlist("system_id") if v.strip()]
    corp_ids = [v for v in request.GET.getlist("corp_id") if v.strip()]
    alliance_ids = [v for v in request.GET.getlist("alliance_id") if v.strip()]

    qs = MapStructure.objects.select_related("map", "solar_system").filter(map__sync_structures=True)

    if system_ids or corp_ids or alliance_ids:
        q = Q()
        if system_ids:
            q |= Q(solar_system__id__in=system_ids)
        if corp_ids:
            q |= Q(owner_id__in=corp_ids)
        if alliance_ids:
            q |= Q(alliance_id__in=alliance_ids)
        qs = qs.filter(q)

    # Pre-populate Tom Select option labels for the selected IDs
    selected_systems = []
    if system_ids:
        selected_systems = list(
            SolarSystem.objects.filter(id__in=system_ids).values("id", "name")
        )

    selected_corps = []
    if corp_ids:
        seen = set()
        for c in EveCorporationInfo.objects.filter(corporation_id__in=corp_ids):
            cid = str(c.corporation_id)
            if cid not in seen:
                seen.add(cid)
                selected_corps.append({"owner_id": cid, "owner_name": c.corporation_name, "owner_ticker": c.corporation_ticker})
        for row in MapStructure.objects.filter(owner_id__in=corp_ids).values("owner_id", "owner_name", "owner_ticker"):
            if row["owner_id"] not in seen:
                seen.add(row["owner_id"])
                selected_corps.append(row)

    selected_alliances = []
    if alliance_ids:
        seen = set()
        for a in EveAllianceInfo.objects.filter(alliance_id__in=alliance_ids):
            aid = str(a.alliance_id)
            if aid not in seen:
                seen.add(aid)
                selected_alliances.append({"alliance_id": aid, "alliance_name": a.alliance_name, "alliance_ticker": a.alliance_ticker})
        for row in MapStructure.objects.filter(alliance_id__in=alliance_ids).values("alliance_id", "alliance_name", "alliance_ticker"):
            if row["alliance_id"] not in seen:
                seen.add(row["alliance_id"])
                selected_alliances.append(row)

    presets = list(StructureFilterPreset.objects.values("id", "name", "solar_system_ids", "corporation_ids", "alliance_ids", "created_by_id"))

    return render(
        request,
        "wanderer/structures.html",
        {
            "active_structures": qs.filter(is_active=True),
            "inactive_structures": qs.filter(is_active=False).order_by("-removed_at"),
            "system_ids": system_ids,
            "corp_ids": corp_ids,
            "alliance_ids": alliance_ids,
            "selected_systems": selected_systems,
            "selected_corps": selected_corps,
            "selected_alliances": selected_alliances,
            "active_filters": bool(system_ids or corp_ids or alliance_ids),
            "presets": presets,
        },
    )


@login_required
@permission_required("wanderer.basic_access")
def autocomplete_solar_systems(request):
    q = request.GET.get("q", "").strip()
    qs = SolarSystem.objects.all()
    if q:
        qs = qs.filter(name__icontains=q)
    rows = qs.order_by("name")[:20]
    results = [{"value": str(r.id), "text": r.name} for r in rows]
    return JsonResponse({"results": results})


@login_required
@permission_required("wanderer.basic_access")
def autocomplete_corporations(request):
    q = request.GET.get("q", "").strip()

    corp_qs = EveCorporationInfo.objects.all()
    if q:
        corp_qs = corp_qs.filter(Q(corporation_name__icontains=q) | Q(corporation_ticker__icontains=q))
    corps = list(corp_qs.order_by("corporation_name")[:20])
    seen_ids = {str(c.corporation_id) for c in corps}
    results = [
        {
            "value": str(c.corporation_id),
            "text": f"{c.corporation_name} [{c.corporation_ticker}]" if c.corporation_ticker else c.corporation_name,
        }
        for c in corps
    ]

    # Supplement with MapStructure data for corps not in EveCorporationInfo
    if len(results) < 20:
        struct_qs = MapStructure.objects.exclude(owner_id="").exclude(owner_name="")
        if q:
            struct_qs = struct_qs.filter(Q(owner_name__icontains=q) | Q(owner_ticker__icontains=q))
        for row in struct_qs.values("owner_id", "owner_name", "owner_ticker").distinct().order_by("owner_name"):
            if row["owner_id"] not in seen_ids and len(results) < 20:
                seen_ids.add(row["owner_id"])
                results.append({
                    "value": row["owner_id"],
                    "text": f"{row['owner_name']} [{row['owner_ticker']}]" if row["owner_ticker"] else row["owner_name"],
                })

    return JsonResponse({"results": results})


@login_required
@permission_required("wanderer.basic_access")
def autocomplete_alliances(request):
    q = request.GET.get("q", "").strip()

    alliance_qs = EveAllianceInfo.objects.all()
    if q:
        alliance_qs = alliance_qs.filter(Q(alliance_name__icontains=q) | Q(alliance_ticker__icontains=q))
    alliances = list(alliance_qs.order_by("alliance_name")[:20])
    seen_ids = {str(a.alliance_id) for a in alliances}
    results = [
        {
            "value": str(a.alliance_id),
            "text": f"{a.alliance_name} [{a.alliance_ticker}]" if a.alliance_ticker else a.alliance_name,
        }
        for a in alliances
    ]

    # Supplement with MapStructure data for alliances not in EveAllianceInfo
    if len(results) < 20:
        struct_qs = MapStructure.objects.exclude(alliance_id="").exclude(alliance_name="")
        if q:
            struct_qs = struct_qs.filter(Q(alliance_name__icontains=q) | Q(alliance_ticker__icontains=q))
        for row in struct_qs.values("alliance_id", "alliance_name", "alliance_ticker").distinct().order_by("alliance_name"):
            if row["alliance_id"] not in seen_ids and len(results) < 20:
                seen_ids.add(row["alliance_id"])
                results.append({
                    "value": row["alliance_id"],
                    "text": f"{row['alliance_name']} [{row['alliance_ticker']}]" if row["alliance_ticker"] else row["alliance_name"],
                })

    return JsonResponse({"results": results})


@login_required
@permission_required("wanderer.basic_access")
@require_POST
def preset_save(request):
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "Invalid JSON"}, status=400)

    name = data.get("name", "").strip()
    if not name:
        return JsonResponse({"error": "Name is required"}, status=400)

    preset, created = StructureFilterPreset.objects.update_or_create(
        name=name,
        defaults={
            "created_by": request.user,
            "solar_system_ids": data.get("solar_system_ids", []),
            "corporation_ids": data.get("corporation_ids", []),
            "alliance_ids": data.get("alliance_ids", []),
        },
    )
    return JsonResponse({
        "id": preset.id,
        "name": preset.name,
        "created": created,
        "solar_system_ids": preset.solar_system_ids,
        "corporation_ids": preset.corporation_ids,
        "alliance_ids": preset.alliance_ids,
        "created_by_id": preset.created_by_id,
    })


@login_required
@permission_required("wanderer.basic_access")
@require_POST
def preset_delete(request, preset_id):
    preset = get_object_or_404(StructureFilterPreset, pk=preset_id)
    if not (request.user.is_staff or preset.created_by_id == request.user.id):
        return JsonResponse({"error": "Permission denied"}, status=403)
    preset.delete()
    return JsonResponse({"ok": True})


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
