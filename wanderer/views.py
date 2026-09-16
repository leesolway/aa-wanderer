"""Views."""

import json
from datetime import timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST
from eve_sde.models import SolarSystem

from allianceauth.eveonline.models import EveAllianceInfo, EveCorporationInfo

from wormholes.models import Effect, EffectModifier, WormholeClass, WormholeSystem
from allianceauth.services.hooks import get_extension_logger

from wanderer.models import (
    Structure,
    StructureFilterPreset,
    WandererAccount,
    WandererManagedMap,
)
from wanderer.tasks import add_alts_to_map, sync_all_map_structures

logger = get_extension_logger(__name__)

# Priority order for choosing which structure's owner to display as "primary" when
# a system has multiple structures. Lower number = shown first.
_STRUCTURE_TYPE_PRIORITY: dict[str, int] = {
    "keepstar": 0,
    "fortizar": 1,
    "astrahus": 2,
    "sotiyo": 3,
    "tatara": 4,
    "athanor": 5,
    "raitaru": 6,
}


def _structure_filters(request) -> tuple[list[str], list[str], list[str]]:
    system_ids = [v for v in request.GET.getlist("system_id") if v.strip()]
    corp_ids = [v for v in request.GET.getlist("corp_id") if v.strip()]
    alliance_ids = [v for v in request.GET.getlist("alliance_id") if v.strip()]
    return system_ids, corp_ids, alliance_ids


def _wh_filters(request) -> tuple[list[str], list[str], list[str]]:
    wh_class_ids = [v for v in request.GET.getlist("wh_class_id") if v.strip()]
    static_leads_to_ids = [v for v in request.GET.getlist("static_leads_to") if v.strip()]
    effect_names = [v for v in request.GET.getlist("effect_name") if v.strip()]
    return wh_class_ids, static_leads_to_ids, effect_names


def _merge_entity_rows(known_rows, structure_qs, id_key, name_key, ticker_key, limit=None):
    """
    Merge {id_key, name_key, ticker_key} dicts already known to AllianceAuth with
    matching rows sourced from Structure (for corps/alliances AA doesn't track,
    e.g. non-member owners of a structure on a tracked map), deduped by id with
    the known rows taking priority. Optionally capped at `limit` rows total.
    """
    seen = set()
    merged = []
    for row in known_rows:
        if row[id_key] in seen:
            continue
        seen.add(row[id_key])
        merged.append(row)
        if limit and len(merged) >= limit:
            return merged
    for row in structure_qs.values(id_key, name_key, ticker_key).distinct():
        if row[id_key] in seen:
            continue
        seen.add(row[id_key])
        merged.append(row)
        if limit and len(merged) >= limit:
            break
    return merged


def _selected_filter_labels(system_ids, corp_ids, alliance_ids):
    """Pre-populate Tom Select option labels for filter values already in the URL."""
    selected_systems = []
    if system_ids:
        selected_systems = list(
            SolarSystem.objects.filter(id__in=system_ids).values("id", "name")
        )

    selected_corps = []
    if corp_ids:
        known = (
            {"owner_id": str(c.corporation_id), "owner_name": c.corporation_name, "owner_ticker": c.corporation_ticker}
            for c in EveCorporationInfo.objects.filter(corporation_id__in=corp_ids)
        )
        selected_corps = _merge_entity_rows(
            known, Structure.objects.filter(owner_id__in=corp_ids), "owner_id", "owner_name", "owner_ticker"
        )

    selected_alliances = []
    if alliance_ids:
        known = (
            {"alliance_id": str(a.alliance_id), "alliance_name": a.alliance_name, "alliance_ticker": a.alliance_ticker}
            for a in EveAllianceInfo.objects.filter(alliance_id__in=alliance_ids)
        )
        selected_alliances = _merge_entity_rows(
            known, Structure.objects.filter(alliance_id__in=alliance_ids), "alliance_id", "alliance_name", "alliance_ticker"
        )

    return selected_systems, selected_corps, selected_alliances


def _resolve_wh_class(solar_system, wh_classes_by_id: dict):
    """Return WormholeClass for a system, falling back to constellation class_id."""
    try:
        wh_class = solar_system.wormhole_info.wormhole_class
    except WormholeSystem.DoesNotExist:
        wh_class = None
    if wh_class is None:
        class_id = (
            solar_system.wormhole_class_id_raw
            or (solar_system.constellation and solar_system.constellation.wormhole_class_id_raw)
        )
        wh_class = wh_classes_by_id.get(class_id)
    return wh_class


@login_required
@permission_required("wanderer.basic_access")
def structures(request):
    """List solar systems that have at least one currently-active structure."""
    system_ids, corp_ids, alliance_ids = _structure_filters(request)
    wh_class_ids, static_leads_to_ids, effect_names = _wh_filters(request)
    filter_mode = request.GET.get("filter_mode", "or")
    if filter_mode not in ("or", "and"):
        filter_mode = "or"

    wh_classes_by_id = {c.class_id: c for c in WormholeClass.objects.all()}

    qs = Structure.objects.filter(is_active=True).select_related(
        "solar_system",
        "solar_system__constellation",
        "solar_system__wormhole_info",
        "solar_system__wormhole_info__effect",
    ).prefetch_related("solar_system__wormhole_info__statics__leads_to")

    if system_ids or corp_ids or alliance_ids:
        if filter_mode == "and":
            if system_ids:
                qs = qs.filter(solar_system__id__in=system_ids)
            if corp_ids:
                qs = qs.filter(owner_id__in=corp_ids)
            if alliance_ids:
                qs = qs.filter(alliance_id__in=alliance_ids)
        else:
            q = Q()
            if system_ids:
                q |= Q(solar_system__id__in=system_ids)
            if corp_ids:
                q |= Q(owner_id__in=corp_ids)
            if alliance_ids:
                q |= Q(alliance_id__in=alliance_ids)
            qs = qs.filter(q)

    if wh_class_ids:
        qs = qs.filter(solar_system__wormhole_info__wormhole_class__class_id__in=wh_class_ids)
    if static_leads_to_ids:
        qs = qs.filter(solar_system__wormhole_info__statics__leads_to__class_id__in=static_leads_to_ids).distinct()
    if effect_names:
        qs = qs.filter(solar_system__wormhole_info__effect__name__in=effect_names)

    systems_by_id = {}
    for s in qs:
        if s.solar_system_id not in systems_by_id:
            wh_class = _resolve_wh_class(s.solar_system, wh_classes_by_id)
            try:
                effect = s.solar_system.wormhole_info.effect
                statics = sorted(s.solar_system.wormhole_info.statics.all(), key=lambda x: x.code)
            except WormholeSystem.DoesNotExist:
                effect = None
                statics = []
            systems_by_id[s.solar_system_id] = {
                "solar_system": s.solar_system,
                "structure_count": 0,
                "corporations": {},
                "alliances": {},
                "last_updated": None,
                "wh_class": wh_class,
                "effect": effect,
                "statics": statics,
            }
        system = systems_by_id[s.solar_system_id]
        system["structure_count"] += 1
        type_priority = _STRUCTURE_TYPE_PRIORITY.get(
            (s.structure_type or "").lower().strip(), 99
        )
        if s.owner_id:
            existing = system["corporations"].get(s.owner_id)
            if existing is None or type_priority < existing["_priority"]:
                system["corporations"][s.owner_id] = {
                    "owner_id": s.owner_id,
                    "owner_name": s.owner_name,
                    "owner_ticker": s.owner_ticker,
                    "_priority": type_priority,
                }
        if s.alliance_id:
            existing = system["alliances"].get(s.alliance_id)
            if existing is None or type_priority < existing["_priority"]:
                system["alliances"][s.alliance_id] = {
                    "alliance_id": s.alliance_id,
                    "alliance_name": s.alliance_name,
                    "alliance_ticker": s.alliance_ticker,
                    "_priority": type_priority,
                }
        if s.last_seen_at and (
            system["last_updated"] is None or s.last_seen_at > system["last_updated"]
        ):
            system["last_updated"] = s.last_seen_at

    modifiers_by_effect: dict[str, list[EffectModifier]] = {}
    for m in EffectModifier.objects.select_related("effect").order_by("-is_positive", "name"):
        modifiers_by_effect.setdefault(m.effect.name, []).append(m)

    systems = []
    for system in systems_by_id.values():
        system["corporations"] = sorted(
            system["corporations"].values(), key=lambda c: (c["_priority"], c["owner_name"])
        )
        system["alliances"] = sorted(
            system["alliances"].values(), key=lambda a: (a["_priority"], a["alliance_name"])
        )
        effect = system["effect"]
        if effect:
            mods = modifiers_by_effect.get(effect.name, [])
            wh_class = system["wh_class"]
            effect_power = wh_class.effect_power if wh_class else None
            lines = [effect.name]
            for m in mods:
                magnitude = m.magnitude_for(effect_power)
                label = f"{m.name}: {magnitude}" if magnitude else m.name
                lines.append(label)
            system["effect_color"] = effect.color or "#6c757d"
            system["effect_tooltip"] = "\n".join(lines)
        systems.append(system)

    # Most recently updated system first. A missing last_updated shouldn't happen
    # (reconcile_structures always sets it) but sorts to the bottom rather than
    # blowing up the comparison if it ever does.
    never_updated = timezone.now() - timedelta(days=36500)
    systems.sort(key=lambda system: system["last_updated"] or never_updated, reverse=True)

    total_structures = sum(s["structure_count"] for s in systems)
    total_systems = len(systems)
    all_corp_ids = set()
    all_alliance_ids = set()
    for s in systems:
        for c in s["corporations"]:
            all_corp_ids.add(c["owner_id"])
        for a in s["alliances"]:
            all_alliance_ids.add(a["alliance_id"])
    total_corps = len(all_corp_ids)
    total_alliances = len(all_alliance_ids)

    selected_systems, selected_corps, selected_alliances = _selected_filter_labels(
        system_ids, corp_ids, alliance_ids
    )
    presets = list(StructureFilterPreset.objects.values(
        "id", "name", "solar_system_ids", "corporation_ids", "alliance_ids",
        "wh_class_ids", "static_leads_to_ids", "effect_names", "filter_mode", "created_by_id",
    ))

    wh_classes_all = list(WormholeClass.objects.filter(
        category__in=[
            WormholeClass.Category.NUMBERED,
            WormholeClass.Category.SHATTERED_FRIGATE,
            WormholeClass.Category.DRIFTER,
            WormholeClass.Category.THERA,
            WormholeClass.Category.POCHVEN,
        ]
    ).order_by("class_id"))
    effects_all = list(Effect.objects.all())

    wh_class_id_set = set(wh_class_ids)
    static_leads_to_id_set = set(static_leads_to_ids)
    selected_wh_classes = [c for c in wh_classes_all if str(c.class_id) in wh_class_id_set]
    selected_static_classes = [c for c in wh_classes_all if str(c.class_id) in static_leads_to_id_set]

    paginator = Paginator(systems, 100)
    try:
        page_number = int(request.GET.get("page", 1))
        if page_number < 1:
            page_number = 1
    except (ValueError, TypeError):
        page_number = 1
    page_obj = paginator.get_page(page_number)

    # Build a query string without the page param so pagination links can append their own.
    base_params = request.GET.copy()
    base_params.pop("page", None)
    base_query_string = base_params.urlencode()

    return render(
        request,
        "wanderer/structures.html",
        {
            "page_obj": page_obj,
            "base_query_string": base_query_string,
            "system_ids": system_ids,
            "corp_ids": corp_ids,
            "alliance_ids": alliance_ids,
            "wh_class_ids": wh_class_ids,
            "static_leads_to_ids": static_leads_to_ids,
            "effect_names": effect_names,
            "selected_systems": selected_systems,
            "selected_corps": selected_corps,
            "selected_alliances": selected_alliances,
            "selected_wh_classes": selected_wh_classes,
            "selected_static_classes": selected_static_classes,
            "active_filters": bool(system_ids or corp_ids or alliance_ids or wh_class_ids or static_leads_to_ids or effect_names),
            "filter_mode": filter_mode,
            "total_structures": total_structures,
            "total_systems": total_systems,
            "total_corps": total_corps,
            "total_alliances": total_alliances,
            "presets": presets,
            "wh_classes_all": wh_classes_all,
            "effects_all": effects_all,
        },
    )


@login_required
@permission_required("wanderer.basic_access")
def system_detail(request, solar_system_id: int):
    """Show every currently-tracked structure (active and previously-seen) in one solar system."""
    solar_system = get_object_or_404(
        SolarSystem.objects.select_related(
            "constellation",
            "wormhole_info__wormhole_class",
            "wormhole_info__effect",
        ),
        pk=solar_system_id,
    )
    try:
        wh_info = solar_system.wormhole_info
        wh_class = wh_info.wormhole_class
        effect = wh_info.effect
    except WormholeSystem.DoesNotExist:
        wh_class = None
        effect = None
    if wh_class is None:
        wh_classes_by_id = {c.class_id: c for c in WormholeClass.objects.all()}
        wh_class = _resolve_wh_class(solar_system, wh_classes_by_id)

    qs = Structure.objects.filter(solar_system=solar_system).select_related(
        "last_source_map"
    )

    return render(
        request,
        "wanderer/system_detail.html",
        {
            "solar_system": solar_system,
            "wh_class": wh_class,
            "effect": effect,
            "active_structures": qs.filter(is_active=True).order_by("-last_seen_at", "name"),
            "inactive_structures": qs.filter(is_active=False).order_by("-removed_at"),
        },
    )


@login_required
@permission_required("wanderer.basic_access")
def structure_history(request, solar_system_id: int, structure_id: int):
    """Return a structure's change history as JSON, for the history modal."""
    structure = get_object_or_404(
        Structure, pk=structure_id, solar_system_id=solar_system_id
    )
    entries = [
        {
            "recorded_at": entry.recorded_at.isoformat(),
            "change_type": entry.get_change_type_display(),
            "changed_fields": entry.changed_fields,
            "owner_name": entry.owner_name,
            "owner_ticker": entry.owner_ticker,
            "alliance_name": entry.alliance_name,
            "alliance_ticker": entry.alliance_ticker,
            "status": entry.status,
            "name": entry.name,
        }
        for entry in structure.history.all()
    ]
    return JsonResponse(
        {
            "structure_name": structure.name,
            "is_active": structure.is_active,
            "entries": entries,
        }
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
    known = (
        {"owner_id": str(c.corporation_id), "owner_name": c.corporation_name, "owner_ticker": c.corporation_ticker}
        for c in corp_qs.order_by("corporation_name")[:20]
    )

    # Supplement with Structure data for corps not in EveCorporationInfo
    struct_qs = Structure.objects.exclude(owner_id="").exclude(owner_name="")
    if q:
        struct_qs = struct_qs.filter(Q(owner_name__icontains=q) | Q(owner_ticker__icontains=q))
    struct_qs = struct_qs.order_by("owner_name")

    rows = _merge_entity_rows(known, struct_qs, "owner_id", "owner_name", "owner_ticker", limit=20)
    results = [
        {
            "value": r["owner_id"],
            "text": f"{r['owner_name']} [{r['owner_ticker']}]" if r["owner_ticker"] else r["owner_name"],
        }
        for r in rows
    ]
    return JsonResponse({"results": results})


@login_required
@permission_required("wanderer.basic_access")
def autocomplete_alliances(request):
    q = request.GET.get("q", "").strip()

    alliance_qs = EveAllianceInfo.objects.all()
    if q:
        alliance_qs = alliance_qs.filter(Q(alliance_name__icontains=q) | Q(alliance_ticker__icontains=q))
    known = (
        {"alliance_id": str(a.alliance_id), "alliance_name": a.alliance_name, "alliance_ticker": a.alliance_ticker}
        for a in alliance_qs.order_by("alliance_name")[:20]
    )

    # Supplement with Structure data for alliances not in EveAllianceInfo
    struct_qs = Structure.objects.exclude(alliance_id="").exclude(alliance_name="")
    if q:
        struct_qs = struct_qs.filter(Q(alliance_name__icontains=q) | Q(alliance_ticker__icontains=q))
    struct_qs = struct_qs.order_by("alliance_name")

    rows = _merge_entity_rows(known, struct_qs, "alliance_id", "alliance_name", "alliance_ticker", limit=20)
    results = [
        {
            "value": r["alliance_id"],
            "text": f"{r['alliance_name']} [{r['alliance_ticker']}]" if r["alliance_ticker"] else r["alliance_name"],
        }
        for r in rows
    ]
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

    filter_mode = data.get("filter_mode", "or")
    if filter_mode not in ("or", "and"):
        filter_mode = "or"

    preset, created = StructureFilterPreset.objects.update_or_create(
        name=name,
        defaults={
            "created_by": request.user,
            "solar_system_ids": data.get("solar_system_ids", []),
            "corporation_ids": data.get("corporation_ids", []),
            "alliance_ids": data.get("alliance_ids", []),
            "wh_class_ids": data.get("wh_class_ids", []),
            "static_leads_to_ids": data.get("static_leads_to_ids", []),
            "effect_names": data.get("effect_names", []),
            "filter_mode": filter_mode,
        },
    )
    return JsonResponse({
        "id": preset.id,
        "name": preset.name,
        "created": created,
        "solar_system_ids": preset.solar_system_ids,
        "corporation_ids": preset.corporation_ids,
        "alliance_ids": preset.alliance_ids,
        "wh_class_ids": preset.wh_class_ids,
        "static_leads_to_ids": preset.static_leads_to_ids,
        "effect_names": preset.effect_names,
        "filter_mode": preset.filter_mode,
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
