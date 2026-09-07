"""Tasks tests"""

from unittest.mock import MagicMock, call, patch

from django.test import TestCase

from wanderer.models import WandererAccount, WandererManagedMap
from wanderer.tasks import (
    add_alts_to_map,
    cleanup_access_list,
    remove_user_characters_from_map,
    sync_all_map_structures,
)

from ..wanderer import AccessListRoles
from .utils import create_managed_map, create_wanderer_users


class TestTasks(TestCase):

    def test_add_character_to_acl(self):
        """Checks that characters properly get added to the access list"""
        WandererManagedMap.get_character_ids_on_access_list = MagicMock(
            return_value=[1001, 1002]
        )  # Creating fake ids to be returned
        WandererManagedMap.add_character_to_acl = MagicMock()
        WandererAccount.get_all_character_ids = MagicMock(
            return_value=[1001, 1003]
        )  # Missing id 1003

        wanderer_map = create_managed_map()
        user = create_wanderer_users(wanderer_map)[0]

        add_alts_to_map(user.id, wanderer_map.id)

        WandererManagedMap.get_character_ids_on_access_list.assert_called_once()
        WandererManagedMap.add_character_to_acl.assert_called_once_with(1003)
        WandererAccount.get_all_character_ids.assert_called_once()

    def test_remove_user_characters_from_acl(self):
        WandererManagedMap.get_character_ids_on_access_list = MagicMock(
            return_value=[1001, 1002, 1003]
        )
        WandererManagedMap.remove_member_from_access_list = MagicMock()
        WandererAccount.get_all_character_ids = MagicMock(return_value=[1001, 1002])

        wanderer_map = create_managed_map()
        user = create_wanderer_users(wanderer_map)[0]

        remove_user_characters_from_map(user.id, wanderer_map.id)

        WandererManagedMap.get_character_ids_on_access_list.assert_called_once()
        WandererAccount.get_all_character_ids.assert_called_once()

        remove_member_calls = [call(1001), call(1002)]
        WandererManagedMap.remove_member_from_access_list.assert_has_calls(
            remove_member_calls, any_order=True
        )

    def test_cleanup_access_list(self):
        WandererManagedMap.get_character_ids_on_access_list = MagicMock(
            return_value=[1000, 1011, 1020]
        )
        WandererManagedMap.remove_member_from_access_list = MagicMock()
        WandererManagedMap.add_character_to_acl = MagicMock()
        WandererManagedMap.get_non_member_characters = MagicMock(
            return_value=[
                (1030, AccessListRoles.VIEWER),
                (1031, AccessListRoles.BLOCKED),
            ]
        )
        WandererManagedMap.set_character_to_member = MagicMock()

        wanderer_map = create_managed_map()
        create_wanderer_users(wanderer_map, 2)

        cleanup_access_list(wanderer_map.id)

        WandererManagedMap.get_character_ids_on_access_list.assert_called_once()
        WandererManagedMap.remove_member_from_access_list.assert_called_once_with(1020)
        add_character_calls = [call(1001), call(1010)]
        WandererManagedMap.add_character_to_acl.assert_has_calls(
            add_character_calls, any_order=True
        )
        WandererManagedMap.get_non_member_characters.assert_called_once()
        set_character_to_member_calls = [call(1030), call(1031)]
        WandererManagedMap.set_character_to_member.assert_has_calls(
            set_character_to_member_calls, any_order=True
        )

    def test_dont_cleanup_access_list(self):
        """Test where the access list is correct and has different roles than member"""
        WandererManagedMap.get_character_ids_on_access_list = MagicMock(
            return_value=[1000, 1001, 1010, 1011]
        )
        WandererManagedMap.get_all_accounts_characters_ids = MagicMock(
            return_value=[1000, 1001, 1010, 1011]
        )
        WandererManagedMap.add_character_to_acl = MagicMock()
        WandererManagedMap.remove_member_from_access_list = MagicMock()
        WandererManagedMap.get_non_member_characters = MagicMock(
            return_value=[
                (1000, AccessListRoles.ADMIN),
                (1001, AccessListRoles.MANAGER),
                (1010, AccessListRoles.MEMBER),
                (1011, AccessListRoles.MEMBER),
            ]
        )
        WandererManagedMap.set_character_to_member = MagicMock()

        wanderer_map = create_managed_map()
        create_wanderer_users(wanderer_map, 2)

        cleanup_access_list(wanderer_map.id)

        WandererManagedMap.get_character_ids_on_access_list.assert_called_once()
        WandererManagedMap.get_all_accounts_characters_ids.assert_called_once()
        WandererManagedMap.add_character_to_acl.assert_not_called()
        WandererManagedMap.remove_member_from_access_list.assert_not_called()
        WandererManagedMap.get_non_member_characters.assert_called_once()
        WandererManagedMap.set_character_to_member.assert_not_called()


class TestSyncAllMapStructures(TestCase):
    """
    Regression coverage for the "owner changed at the source but our Structure
    rows never update" bug: sync_all_map_structures used to fan the per-map syncs
    out through a Celery chord and rely on its callback to run reconciliation.
    This project has no CELERY_RESULT_BACKEND configured, so the chord callback
    (reconcile_all_structures) silently never fired - MapStructure kept getting
    refreshed (the header tasks still ran fine) but nothing ever reconciled it
    into the Structure rows the UI actually shows.

    sync_all_map_structures must instead call sync_map_structures directly (a
    plain function call, not .delay()/.si()) for each enabled map, then call
    reconcile_structures() directly too - no Celery group/chord involved.
    """

    @patch("wanderer.tasks.reconcile_structures")
    @patch("wanderer.tasks.sync_map_structures")
    def test_syncs_each_enabled_map_directly_then_reconciles(
        self, mock_sync_map_structures, mock_reconcile_structures
    ):
        enabled_map = create_managed_map()
        enabled_map.sync_structures = True
        enabled_map.save()

        disabled_map = WandererManagedMap.objects.create(
            wanderer_url="http://wanderer-disabled.localhost",
            map_slug="test-disabled",
            map_api_key="bad-map-api-key",
            map_acl_id="ACL_UUID_DISABLED",
            map_acl_api_key="bad-acl-api-key",
            sync_structures=False,
        )

        sync_all_map_structures()

        # Called directly (not .si()/.delay()) with just the map id - if this
        # regresses back to a chord/group, the mock itself is never called this
        # way (only a .si/.delay attribute on it would be), so this fails loudly.
        mock_sync_map_structures.assert_called_once_with(enabled_map.id)
        mock_reconcile_structures.assert_called_once()

    @patch("wanderer.tasks.reconcile_structures")
    @patch("wanderer.tasks.sync_map_structures")
    def test_reconciles_even_with_no_enabled_maps(
        self, mock_sync_map_structures, mock_reconcile_structures
    ):
        """reconcile_structures must run unconditionally - the old
        `if tasks: chord(...)` shape skipped reconciliation entirely whenever no
        map had sync enabled."""
        sync_all_map_structures()

        mock_sync_map_structures.assert_not_called()
        mock_reconcile_structures.assert_called_once()
