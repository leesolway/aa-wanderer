"""Tests for wanderer.structures.reconcile_structures()."""

from django.test import TestCase
from django.utils import timezone
from eve_sde.models import SolarSystem

from wanderer.models import MapStructure, Structure, StructureHistory
from wanderer.structures import reconcile_structures

from .utils import create_managed_map


def create_map_structure(
    map_obj,
    solar_system,
    *,
    wanderer_id,
    name="Test Keepstar",
    structure_type="Keepstar",
    structure_type_id="35834",
    owner_name="Test Corp",
    owner_ticker="TEST",
    owner_id="1000001",
    alliance_name="",
    alliance_ticker="",
    alliance_id="",
    status="",
    is_active=True,
    structure_updated_at=None,
) -> MapStructure:
    return MapStructure.objects.create(
        wanderer_id=wanderer_id,
        map=map_obj,
        name=name,
        structure_type=structure_type,
        structure_type_id=structure_type_id,
        solar_system=solar_system,
        owner_name=owner_name,
        owner_ticker=owner_ticker,
        owner_id=owner_id,
        alliance_name=alliance_name,
        alliance_ticker=alliance_ticker,
        alliance_id=alliance_id,
        status=status,
        is_active=is_active,
        structure_updated_at=structure_updated_at,
    )


class TestReconcileStructures(TestCase):
    def setUp(self):
        self.solar_system = SolarSystem.objects.create(id=30000142, name="Jita")
        self.map_a = create_managed_map()
        self.map_b = create_managed_map()
        self.map_b.wanderer_url = "http://wanderer-b.localhost"
        self.map_b.save()

    def test_creates_structure_from_single_map(self):
        create_map_structure(self.map_a, self.solar_system, wanderer_id="a-1")

        reconcile_structures()

        self.assertEqual(Structure.objects.count(), 1)
        structure = Structure.objects.get()
        self.assertEqual(structure.name, "Test Keepstar")
        self.assertTrue(structure.is_active)
        self.assertEqual(structure.last_source_map, self.map_a)
        self.assertEqual(StructureHistory.objects.count(), 0)

    def test_same_structure_on_two_maps_collapses_to_one_using_freshest(self):
        now = timezone.now()
        create_map_structure(
            self.map_a,
            self.solar_system,
            wanderer_id="a-1",
            owner_name="Stale Corp",
            structure_updated_at=now - timezone.timedelta(days=1),
        )
        create_map_structure(
            self.map_b,
            self.solar_system,
            wanderer_id="b-1",
            owner_name="Fresh Corp",
            structure_updated_at=now,
        )

        reconcile_structures()

        self.assertEqual(Structure.objects.count(), 1)
        structure = Structure.objects.get()
        self.assertEqual(structure.owner_name, "Fresh Corp")
        self.assertEqual(structure.last_source_map, self.map_b)

    def test_last_seen_at_reflects_source_freshness_not_reconcile_time(self):
        """
        Regression test: last_seen_at must come from the winning MapStructure row's
        own freshness() (structure_updated_at/inserted_at/last_synced), not from
        `timezone.now()` at the moment reconcile_structures() happened to run -
        otherwise every structure ends up stamped with the same reconciliation-pass
        timestamp instead of when its data was actually last input.
        """
        old_timestamp = timezone.now() - timezone.timedelta(days=10)
        create_map_structure(
            self.map_a,
            self.solar_system,
            wanderer_id="a-1",
            structure_updated_at=old_timestamp,
        )

        reconcile_structures()

        structure = Structure.objects.get()
        self.assertAlmostEqual(
            structure.last_seen_at, old_timestamp, delta=timezone.timedelta(seconds=1)
        )

    def test_owner_change_is_archived_to_history(self):
        create_map_structure(self.map_a, self.solar_system, wanderer_id="a-1", owner_name="Old Corp")
        reconcile_structures()

        MapStructure.objects.filter(wanderer_id="a-1").update(owner_name="New Corp")
        reconcile_structures()

        structure = Structure.objects.get()
        self.assertEqual(structure.owner_name, "New Corp")
        history = StructureHistory.objects.get()
        self.assertEqual(history.change_type, StructureHistory.ChangeType.UPDATED)
        self.assertEqual(history.owner_name, "Old Corp")
        self.assertIn("owner_name", history.changed_fields)

    def test_removal_from_all_maps_marks_inactive_and_archives(self):
        create_map_structure(self.map_a, self.solar_system, wanderer_id="a-1")
        reconcile_structures()

        MapStructure.objects.filter(wanderer_id="a-1").update(is_active=False)
        reconcile_structures()

        structure = Structure.objects.get()
        self.assertFalse(structure.is_active)
        self.assertIsNotNone(structure.removed_at)
        history = StructureHistory.objects.get()
        self.assertEqual(history.change_type, StructureHistory.ChangeType.REMOVED)

    def test_reappearance_after_removal(self):
        create_map_structure(self.map_a, self.solar_system, wanderer_id="a-1")
        reconcile_structures()
        MapStructure.objects.filter(wanderer_id="a-1").update(is_active=False)
        reconcile_structures()

        MapStructure.objects.filter(wanderer_id="a-1").update(is_active=True)
        reconcile_structures()

        structure = Structure.objects.get()
        self.assertTrue(structure.is_active)
        self.assertIsNone(structure.removed_at)
        reappeared = StructureHistory.objects.filter(
            change_type=StructureHistory.ChangeType.REAPPEARED
        )
        self.assertEqual(reappeared.count(), 1)

    def test_structure_still_seen_on_another_map_is_not_removed(self):
        """If map A stops reporting a structure but map B still does, it stays active."""
        create_map_structure(self.map_a, self.solar_system, wanderer_id="a-1")
        create_map_structure(self.map_b, self.solar_system, wanderer_id="b-1")
        reconcile_structures()

        MapStructure.objects.filter(wanderer_id="a-1").update(is_active=False)
        reconcile_structures()

        structure = Structure.objects.get()
        self.assertTrue(structure.is_active)
        self.assertEqual(
            StructureHistory.objects.filter(
                change_type=StructureHistory.ChangeType.REMOVED
            ).count(),
            0,
        )

    def test_different_structure_type_in_same_system_and_name_stays_distinct(self):
        create_map_structure(
            self.map_a, self.solar_system, wanderer_id="a-1",
            structure_type="Astrahus", structure_type_id="35832",
        )
        create_map_structure(
            self.map_a, self.solar_system, wanderer_id="a-2",
            structure_type="Keepstar", structure_type_id="35834",
        )

        reconcile_structures()

        self.assertEqual(Structure.objects.count(), 2)
