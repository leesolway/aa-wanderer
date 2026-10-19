from django.contrib.auth.models import Group
from django.test import TestCase

from app_utils.testing import create_fake_user

from wanderer.auth_hooks import WandererManagedMapService
from wanderer.tests.utils import create_managed_map


def create_map_hook(managed_map) -> WandererManagedMapService:
    """Instance a per-map hook the same way add_del_callback() does"""
    hook_class = type(
        f"WandererManagedMapService'{managed_map}'",
        (WandererManagedMapService,),
        {},
        managed_map=managed_map,
    )
    return hook_class()


class TestShowServiceCtrl(TestCase):
    """Which maps the services page lists for a given user"""

    def setUp(self):
        self.managed_map = create_managed_map()
        self.hook = create_map_hook(self.managed_map)
        self.group = Group.objects.create(name="map access")
        self.managed_map.group_access.add(self.group)

    def test_shown_to_user_with_access(self):
        user = create_fake_user(
            1001, "with access", permissions=["wanderer.basic_access"]
        )
        user.groups.add(self.group)

        self.assertTrue(self.hook.show_service_ctrl(user))

    def test_hidden_from_user_without_access(self):
        user = create_fake_user(
            1002, "no group", permissions=["wanderer.basic_access"]
        )

        self.assertFalse(self.hook.show_service_ctrl(user))

    def test_hidden_from_user_without_permission(self):
        user = create_fake_user(1003, "no permission")
        user.groups.add(self.group)

        self.assertFalse(self.hook.show_service_ctrl(user))

    def test_shown_to_superuser_without_access(self):
        """
        Superusers see every map panel whether or not they have access, per
        the base hook's `service_active_for_user(user) or user.is_superuser`.
        """
        user = create_fake_user(1004, "superuser no main")
        user.is_superuser = True
        user.save()
        user.profile.main_character = None
        user.profile.save()

        self.assertFalse(self.managed_map.accessible_by(user))
        self.assertTrue(self.hook.show_service_ctrl(user))
