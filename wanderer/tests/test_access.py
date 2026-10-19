from django.contrib.auth.models import Group
from django.test import TestCase

from app_utils.testing import create_fake_user

from wanderer.models import WandererManagedMap


def create_map(name, slug) -> WandererManagedMap:
    return WandererManagedMap.objects.create(
        name=name,
        wanderer_url="http://wanderer.localhost",
        map_slug=slug,
        map_api_key="bad-map-api-key",
        map_acl_id="ACL_UUID",
        map_acl_api_key="bad-acl-api-key",
    )


class TestAccessibleBy(TestCase):
    """
    Row level access: basic_access alone grants nothing, a map is only
    reachable through an access entry that matches the user.
    """

    def setUp(self):
        self.r2 = Group.objects.create(name="R2")
        self.r3 = Group.objects.create(name="R3")

        self.r2_map = create_map("R2 Map", "r2map")
        self.r2_map.group_access.add(self.r2)

        self.r3_map = create_map("R3 Map", "r3map")
        self.r3_map.group_access.add(self.r3)

        self.user = create_fake_user(
            1001, "member", permissions=["wanderer.basic_access"]
        )
        self.user.groups.add(self.r2)

    def test_member_sees_only_their_group_map(self):
        self.assertTrue(self.r2_map.accessible_by(self.user))
        self.assertFalse(self.r3_map.accessible_by(self.user))

    def test_basic_access_alone_grants_nothing(self):
        """A map restricted to a group the user isn't in stays out of reach"""
        loner = create_fake_user(
            1002, "no groups", permissions=["wanderer.basic_access"]
        )

        self.assertFalse(self.r2_map.accessible_by(loner))
        self.assertFalse(self.r3_map.accessible_by(loner))

    def test_no_access_entries_at_all(self):
        """A map nobody has been granted is reachable by nobody"""
        empty = create_map("Empty", "empty")

        self.assertFalse(empty.accessible_by(self.user))

    def test_superuser_reaches_every_map(self):
        admin = create_fake_user(1003, "admin")
        admin.is_superuser = True
        admin.save()

        self.assertTrue(self.r2_map.accessible_by(admin))
        self.assertTrue(self.r3_map.accessible_by(admin))
