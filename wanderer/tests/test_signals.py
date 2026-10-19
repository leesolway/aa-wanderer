"""Tests for Astropath ACL sync signals."""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, User
from django.test import TestCase

from wanderer.models import AstropathACLMapping


def _make_mapping(group: Group, acl_id: int, role: str = "viewer") -> AstropathACLMapping:
    return AstropathACLMapping.objects.create(group=group, acl_id=acl_id, role=role)


class TestGroupMembershipSignal(TestCase):

    def setUp(self):
        self.group = Group.objects.create(name="Mapped Group")
        self.unmapped_group = Group.objects.create(name="Unmapped Group")
        _make_mapping(self.group, acl_id=10)
        self.user = User.objects.create_user("pilot")

    @patch("wanderer.signals.sync_astropath_acl")
    def test_sync_queued_when_user_added_to_mapped_group(self, mock_task):
        self.user.groups.add(self.group)
        mock_task.delay.assert_called_once_with(10)

    @patch("wanderer.signals.sync_astropath_acl")
    def test_sync_queued_when_user_removed_from_mapped_group(self, mock_task):
        self.user.groups.add(self.group)
        mock_task.reset_mock()

        self.user.groups.remove(self.group)
        mock_task.delay.assert_called_once_with(10)

    @patch("wanderer.signals.sync_astropath_acl")
    def test_no_sync_for_unmapped_group(self, mock_task):
        self.user.groups.add(self.unmapped_group)
        mock_task.delay.assert_not_called()

    @patch("wanderer.signals.sync_astropath_acl")
    def test_sync_queued_via_group_user_set(self, mock_task):
        """Also handles group.user_set.add(user) direction."""
        self.group.user_set.add(self.user)
        mock_task.delay.assert_called_once_with(10)


class TestUserDeleteSignal(TestCase):

    def setUp(self):
        self.group = Group.objects.create(name="Mapped Group")
        _make_mapping(self.group, acl_id=20)
        self.user = User.objects.create_user("doomed")
        self.user.groups.add(self.group)

    @patch("wanderer.signals.sync_astropath_acl")
    def test_sync_queued_when_user_deleted(self, mock_task):
        mock_task.reset_mock()
        self.user.delete()
        mock_task.delay.assert_called_once_with(20)


class TestProfileSaveSignal(TestCase):

    def setUp(self):
        self.group = Group.objects.create(name="Mapped Group")
        _make_mapping(self.group, acl_id=30)
        self.user = User.objects.create_user("mapper")
        self.user.groups.add(self.group)

    @patch("wanderer.signals.sync_astropath_acl")
    def test_sync_queued_on_full_profile_save(self, mock_task):
        mock_task.reset_mock()
        self.user.profile.save()
        mock_task.delay.assert_called_once_with(30)

    @patch("wanderer.signals.sync_astropath_acl")
    def test_sync_queued_when_main_character_in_update_fields(self, mock_task):
        mock_task.reset_mock()
        self.user.profile.save(update_fields=["main_character_id"])
        mock_task.delay.assert_called_once_with(30)

    @patch("wanderer.signals.sync_astropath_acl")
    def test_no_sync_when_unrelated_field_saved(self, mock_task):
        mock_task.reset_mock()
        self.user.profile.save(update_fields=["language"])
        mock_task.delay.assert_not_called()
