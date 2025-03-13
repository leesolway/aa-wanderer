from unittest.mock import MagicMock, call

from django.db import IntegrityError
from django.test import TestCase

from wanderer.models import WandererManagedMap
from wanderer.tests.utils import create_managed_map, create_wanderer_users
from wanderer.wanderer import NotFoundError


class TestMap(TestCase):

    def test_same_map(self):
        """Cancels creating 2 maps with the same name/slug combination"""
        WandererManagedMap.objects.create(
            wanderer_url="fake_url",
            map_slug="slug",
            map_api_key="fake_key",
            map_acl_id="id",
            map_acl_api_key="fake_key",
        )

        self.assertRaises(
            IntegrityError,
            WandererManagedMap.objects.create,
            wanderer_url="fake_url",
            map_slug="slug",
            map_api_key="fake_key",
            map_acl_id="id",
            map_acl_api_key="fake_key",
        )

    def test_get_all_accounts_characters_ids(self):
        managed_map = create_managed_map()
        create_wanderer_users(managed_map, 2)

        all_character_ids = managed_map.get_all_accounts_characters_ids()

        self.assertEqual(len(all_character_ids), 4)
        self.assertIn(1000, all_character_ids)
        self.assertIn(1001, all_character_ids)
        self.assertIn(1010, all_character_ids)
        self.assertIn(1011, all_character_ids)

    def test_get_user_account(self):
        managed_map_1 = create_managed_map()
        managed_map_2 = WandererManagedMap.objects.create(
            wanderer_url="http://wanderer.localhost",
            map_slug="test2",
            map_api_key="bad-map-api-key",
            map_acl_id="ACL_UUID",
            map_acl_api_key="bad-acl-api-key",
        )
        wanderer_account = create_wanderer_users(managed_map_1)[0]
        user = wanderer_account.user

        self.assertIsNone(managed_map_2.get_user_account(user))
        self.assertEqual(wanderer_account, managed_map_1.get_user_account(user))

    def test_delete_user(self):
        # First char id will be considered ok
        # The second one will be considered as not part of the access list and return a none
        WandererManagedMap.remove_member_from_access_list = MagicMock(
            side_effect=(None, NotFoundError)
        )

        managed_map = create_managed_map()
        wanderer_account = create_wanderer_users(managed_map)[0]
        user = wanderer_account.user

        managed_map.delete_user(user)

        remove_member_calls = [call(1000), call(1010)]
        WandererManagedMap.remove_member_from_access_list.assert_has_calls(
            remove_member_calls, any_order=True
        )
