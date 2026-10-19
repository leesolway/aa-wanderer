"""Tests for syncing AA groups to Astropath ACLs."""

from unittest.mock import MagicMock, patch

from django.contrib.auth.models import Group, User
from django.test import TestCase, override_settings

from wanderer.astropath import (
    AstropathConflictError,
    AstropathNotConfiguredError,
    _build_entries,
    sync_acl,
)
from wanderer.models import AstropathConfiguration


def _config(**kwargs) -> AstropathConfiguration:
    defaults = {"url": "https://ap.localhost/", "api_key": "ap_test"}
    defaults.update(kwargs)
    return AstropathConfiguration.objects.create(**defaults)


def _response(status_code: int, body: dict) -> MagicMock:
    r = MagicMock(status_code=status_code)
    r.json.return_value = body
    if status_code >= 400:
        r.raise_for_status.side_effect = Exception(f"HTTP {status_code}")
    else:
        r.raise_for_status = MagicMock()
    return r


def _conflict() -> MagicMock:
    r = MagicMock(status_code=409)
    r.json.return_value = {"code": "stale_revision"}
    r.raise_for_status = MagicMock()
    return r


ENTRIES_RESPONSE = {"revision": 1, "entries": []}
SYNC_RESULT = {"revision": 2, "entryCount": 1, "added": 1, "removed": 0, "changed": 0}


def _make_user_with_main(username: str, char_id: int, group: Group) -> User:
    """Creates a User with a mocked profile.main_character and adds them to a group."""
    user = User.objects.create_user(username)
    user.groups.add(group)
    # Patch the profile relation inline
    main = MagicMock()
    main.character_id = char_id
    user.profile = MagicMock()
    user.profile.main_character = main
    return user


class TestSyncAcl(TestCase):

    def setUp(self):
        self.config = _config()
        self.group = Group.objects.create(name="Test Group")

    @patch("wanderer.astropath.time.time", return_value=1_700_000_000.0)
    @patch("wanderer.astropath.requests.put")
    def test_puts_with_timestamp_revision(self, mock_put, mock_time):
        mock_put.return_value = _response(200, SYNC_RESULT)

        sync_acl(42, [(self.group.id, "viewer")])

        mock_put.assert_called_once_with(
            "https://ap.localhost/external/v1/access-lists/42/entries",
            json={"revision": 1_700_000_000_000, "entries": []},
            headers={"Authorization": "Bearer ap_test"},
            timeout=30,
        )

    @patch("wanderer.astropath.time.time", return_value=1_700_000_000.0)
    @patch("wanderer.astropath.requests.put")
    def test_conflict_is_skipped_not_retried(self, mock_put, mock_time):
        """A 409 means a newer sync already ran — we should drop this attempt."""
        mock_put.return_value = _conflict()

        result = sync_acl(42, [(self.group.id, "viewer")])

        self.assertEqual(mock_put.call_count, 1)
        self.assertEqual(result, {})

    @patch("wanderer.astropath.requests.put")
    def test_no_get_is_issued(self, mock_put):
        """sync_acl must not call GET /entries — revision comes from the clock."""
        mock_put.return_value = _response(200, SYNC_RESULT)

        with patch("wanderer.astropath.requests.get") as mock_get:
            sync_acl(42, [(self.group.id, "viewer")])
            mock_get.assert_not_called()

    def test_not_configured(self):
        AstropathConfiguration.objects.all().delete()
        with self.assertRaises(AstropathNotConfiguredError):
            sync_acl(42, [])


class TestBuildEntries(TestCase):

    def setUp(self):
        self.group_a = Group.objects.create(name="Group A")
        self.group_b = Group.objects.create(name="Group B")

    def _user_with_main(self, username: str, char_id: int) -> User:
        user = User.objects.create_user(username)
        main = MagicMock()
        main.character_id = char_id
        user.profile = MagicMock()
        user.profile.main_character = main
        return user

    def test_main_only_sent(self):
        user = self._user_with_main("alpha", 93000001)
        user.groups.add(self.group_a)

        with patch("wanderer.astropath.User.objects.filter") as mock_filter:
            mock_filter.return_value.select_related.return_value.distinct.return_value = [user]
            entries = _build_entries([(self.group_a.id, "viewer")])

        self.assertEqual(entries, [{"subjectType": "character", "subjectId": 93000001, "role": "viewer"}])

    def test_user_without_main_skipped(self):
        user = User.objects.create_user("nochar")
        user.profile = MagicMock()
        user.profile.main_character = None
        user.groups.add(self.group_a)

        with patch("wanderer.astropath.User.objects.filter") as mock_filter:
            mock_filter.return_value.select_related.return_value.distinct.return_value = [user]
            entries = _build_entries([(self.group_a.id, "viewer")])

        self.assertEqual(entries, [])

    def test_highest_role_wins(self):
        user = self._user_with_main("beta", 93000002)
        user.groups.set([self.group_a, self.group_b])

        def fake_filter(**kwargs):
            qs = MagicMock()
            qs.select_related.return_value.distinct.return_value = [user]
            return qs

        with patch("wanderer.astropath.User.objects.filter", side_effect=fake_filter):
            entries = _build_entries([(self.group_a.id, "viewer"), (self.group_b.id, "editor")])

        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["role"], "editor")
