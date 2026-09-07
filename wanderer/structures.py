"""
Reconciliation of per-map structure syncs into a single, deduplicated, historized
view.

MapStructure rows are the raw ingest log: one row per (map, wanderer_id), refreshed
every time wanderer.tasks.sync_map_structures runs for that map. Wanderer's own
structure id is only unique within a single map's own database, so the same
real-world structure reported by two different maps shows up as two unrelated
MapStructure rows.

reconcile_structures() collapses those rows into Structure - one row per real
structure, identified by (solar_system, name, structure_type_id) - using whichever
contributing MapStructure row has the freshest data. Every detected change (and
every removal) is archived to StructureHistory before it's overwritten, so the
current Structure row plus its history gives a full timeline.

This is a plain function (not a Celery task) so it can be called the same way from
the periodic sync task, a management command, and the initial data migration.
"""

from collections import defaultdict
from datetime import timedelta

from django.utils import timezone

from allianceauth.services.hooks import get_extension_logger

from wanderer.models import (
    STRUCTURE_TRACKED_FIELDS,
    MapStructure,
    Structure,
    StructureHistory,
)

logger = get_extension_logger(__name__)


def _group_key(row: MapStructure) -> tuple:
    return (row.solar_system_id, row.name, row.structure_type_id)


def _archive(
    structure: Structure, change_type: str, changed_fields: list[str]
) -> None:
    """Snapshot a Structure's current field values to StructureHistory before they change."""
    StructureHistory.objects.create(
        structure=structure,
        change_type=change_type,
        changed_fields=changed_fields,
        **{field: getattr(structure, field) for field in STRUCTURE_TRACKED_FIELDS},
    )


def reconcile_structures() -> None:
    """
    Rebuild the Structure/StructureHistory tables from the currently-active
    MapStructure rows across every map.
    """
    active_rows = MapStructure.objects.filter(
        is_active=True, solar_system__isnull=False
    ).select_related("map")

    groups: dict[tuple, list[MapStructure]] = defaultdict(list)
    for row in active_rows:
        groups[_group_key(row)].append(row)

    now = timezone.now()
    # Fallback for rows with no usable timestamp at all, kept aware to stay comparable
    # with real freshness() values (a naive datetime.min would blow up that comparison).
    no_timestamp_fallback = now - timedelta(days=3650)
    seen_keys = set()
    created_count = 0
    updated_count = 0

    for key, rows in groups.items():
        solar_system_id, name, structure_type_id = key
        latest = max(rows, key=lambda r: r.freshness() or no_timestamp_fallback)
        seen_keys.add(key)

        latest_freshness = latest.freshness() or no_timestamp_fallback

        structure, created = Structure.objects.get_or_create(
            solar_system_id=solar_system_id,
            name=name,
            structure_type_id=structure_type_id,
            defaults={
                "structure_type": latest.structure_type,
                "owner_name": latest.owner_name,
                "owner_ticker": latest.owner_ticker,
                "owner_id": latest.owner_id,
                "alliance_name": latest.alliance_name,
                "alliance_ticker": latest.alliance_ticker,
                "alliance_id": latest.alliance_id,
                "status": latest.status,
                "end_time": latest.end_time,
                "notes": latest.notes,
                "last_seen_at": latest_freshness,
                "last_source_map": latest.map,
                "is_active": True,
            },
        )

        if created:
            created_count += 1
            continue

        changed_fields = [
            field
            for field in STRUCTURE_TRACKED_FIELDS
            if getattr(structure, field) != getattr(latest, field)
        ]
        was_inactive = not structure.is_active

        if changed_fields or was_inactive:
            _archive(
                structure,
                StructureHistory.ChangeType.REAPPEARED
                if was_inactive
                else StructureHistory.ChangeType.UPDATED,
                changed_fields,
            )
            for field in STRUCTURE_TRACKED_FIELDS:
                setattr(structure, field, getattr(latest, field))
            structure.is_active = True
            structure.removed_at = None
            updated_count += 1

        structure.last_seen_at = latest_freshness
        structure.last_source_map = latest.map
        structure.save()

    removed_count = 0
    still_active = Structure.objects.filter(is_active=True)
    for structure in still_active:
        key = (structure.solar_system_id, structure.name, structure.structure_type_id)
        if key in seen_keys:
            continue
        _archive(structure, StructureHistory.ChangeType.REMOVED, [])
        structure.is_active = False
        structure.removed_at = now
        structure.save()
        removed_count += 1

    logger.info(
        "Structure reconciliation: %d groups, %d created, %d updated, %d removed",
        len(groups),
        created_count,
        updated_count,
        removed_count,
    )
