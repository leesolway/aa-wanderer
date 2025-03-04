from django.db import IntegrityError
from django.test import TestCase

from wanderer.models import WandererManagedMap
from wanderer.tests.utils import create_managed_map, create_wanderer_users


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
