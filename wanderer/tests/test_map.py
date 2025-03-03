from django.db import IntegrityError
from django.test import TestCase

from wanderer.models import WandererManagedMap


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
