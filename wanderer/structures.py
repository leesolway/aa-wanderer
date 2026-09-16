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

    # Pre-fetch all existing Structure rows in one query instead of get_or_create per group.
    existing_by_key: dict[tuple, Structure] = {
        (s.solar_system_id, s.name, s.structure_type_id): s
        for s in Structure.objects.all()
    }

    seen_keys: set[tuple] = set()
    new_structures: list[Structure] = []
    structures_to_update: list[Structure] = []
    histories_to_create: list[StructureHistory] = []
    updated_count = 0

    for key, rows in groups.items():
        solar_system_id, name, structure_type_id = key
        latest = max(rows, key=lambda r: r.freshness() or no_timestamp_fallback)
        seen_keys.add(key)
        latest_freshness = latest.freshness() or no_timestamp_fallback

        existing = existing_by_key.get(key)
        if existing is None:
            new_struct = Structure(
                solar_system_id=solar_system_id,
                name=name,
                structure_type_id=structure_type_id,
                structure_type=latest.structure_type,
                owner_name=latest.owner_name,
                owner_ticker=latest.owner_ticker,
                owner_id=latest.owner_id,
                alliance_name=latest.alliance_name,
                alliance_ticker=latest.alliance_ticker,
                alliance_id=latest.alliance_id,
                status=latest.status,
                end_time=latest.end_time,
                notes=latest.notes,
                last_seen_at=latest_freshness,
                last_source_map=latest.map,
                is_active=True,
            )
            new_structures.append(new_struct)
            continue

        changed_fields = [
            field
            for field in STRUCTURE_TRACKED_FIELDS
            if getattr(existing, field) != getattr(latest, field)
        ]
        was_inactive = not existing.is_active

        if changed_fields or was_inactive:
            histories_to_create.append(
                StructureHistory(
                    structure=existing,
                    change_type=(
                        StructureHistory.ChangeType.REAPPEARED
                        if was_inactive
                        else StructureHistory.ChangeType.UPDATED
                    ),
                    changed_fields=changed_fields,
                    **{field: getattr(existing, field) for field in STRUCTURE_TRACKED_FIELDS},
                )
            )
            for field in STRUCTURE_TRACKED_FIELDS:
                setattr(existing, field, getattr(latest, field))
            existing.is_active = True
            existing.removed_at = None
            updated_count += 1

        existing.last_seen_at = latest_freshness
        existing.last_source_map = latest.map
        structures_to_update.append(existing)

    # Detect removals from the pre-fetched dict — no extra query needed.
    removed_count = 0
    for key, existing in existing_by_key.items():
        if key not in seen_keys and existing.is_active:
            histories_to_create.append(
                StructureHistory(
                    structure=existing,
                    change_type=StructureHistory.ChangeType.REMOVED,
                    changed_fields=[],
                    **{field: getattr(existing, field) for field in STRUCTURE_TRACKED_FIELDS},
                )
            )
            existing.is_active = False
            existing.removed_at = now
            structures_to_update.append(existing)
            removed_count += 1

    # Execute all changes in bulk — O(1) queries regardless of structure count.
    # bulk_create returns objects with PKs populated (PostgreSQL always; Django ≥4.1 for others),
    # which lets us immediately create CREATED history entries without a round-trip.
    created_structures = Structure.objects.bulk_create(new_structures)
    for new_struct in created_structures:
        histories_to_create.append(
            StructureHistory(
                structure=new_struct,
                change_type=StructureHistory.ChangeType.CREATED,
                changed_fields=[],
                **{field: getattr(new_struct, field) for field in STRUCTURE_TRACKED_FIELDS},
            )
        )
    if structures_to_update:
        Structure.objects.bulk_update(
            structures_to_update,
            fields=STRUCTURE_TRACKED_FIELDS + ["is_active", "removed_at", "last_seen_at", "last_source_map"],
        )
    if histories_to_create:
        StructureHistory.objects.bulk_create(histories_to_create)

    logger.info(
        "Structure reconciliation: %d groups, %d created, %d updated, %d removed",
        len(groups),
        len(new_structures),
        updated_count,
        removed_count,
    )
