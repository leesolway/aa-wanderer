import responses
from responses import matchers

from django.test import TestCase

from wanderer.wanderer import (
    AccessListRoles,
    BadAPIKeyError,
    NotFoundError,
    OwnerEveIdDoesNotExistError,
    add_character_to_acl,
    create_acl_associated_to_map,
    get_acl_member_ids,
    get_non_member_characters,
    remove_member_from_access_list,
    set_character_to_member,
)


class TestApi(TestCase):

    @responses.activate
    def test_create_acl_linked_to_map(self):
        responses.post(
            "http://wanderer.localhost/api/map/acls",
            match=[
                matchers.json_params_matcher(
                    {
                        "acl": {
                            "name": "AA ACL test",
                            "description": "Access list managed by aa-wanderer for the map test. Do not manually edit.",
                            "owner_eve_id": "1",
                        }
                    }
                ),
                matchers.header_matcher({"Authorization": "Bearer dummy-api-key"}),
                matchers.query_param_matcher({"slug": "test"}),
            ],
            json={
                "data": {
                    "id": "095be4ad-6ab4-4024-89b1-7846e25132c6",
                    "name": "test - Auth managed Access list",
                    "description": "Access list managed by alliance auth. Do not manually edit.",
                    "members": [],
                    "inserted_at": "2025-02-17T21:24:44.454134Z",
                    "updated_at": "2025-02-17T21:24:44.454134Z",
                    "api_key": "4620ba44-0930-4410-a513-b4cf51780cfb",
                    "owner_id": "aa49f1b7-35de-4fee-9a9a-8165d52ca8bc",
                }
            },
        )

        api_id, api_key = create_acl_associated_to_map(
            "http://wanderer.localhost", "test", 1, "dummy-api-key"
        )

        self.assertEqual("095be4ad-6ab4-4024-89b1-7846e25132c6", api_id)
        self.assertEqual("4620ba44-0930-4410-a513-b4cf51780cfb", api_key)

    @responses.activate
    def test_create_acl_wrong_token(self):
        responses.post(
            "http://wanderer.localhost/api/map/acls",
            match=[
                matchers.json_params_matcher(
                    {
                        "acl": {
                            "name": "AA ACL test",
                            "description": "Access list managed by aa-wanderer for the map test. Do not manually edit.",
                            "owner_eve_id": "1",
                        }
                    }
                ),
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
                matchers.query_param_matcher({"slug": "test"}),
            ],
            status=401,
        )

        self.assertRaises(
            BadAPIKeyError,
            create_acl_associated_to_map,
            "http://wanderer.localhost",
            "test",
            1,
            "bad-api-key",
        )

    @responses.activate
    def test_get_character_ids_on_access_list(self):
        responses.get(
            "http://wanderer.localhost/api/acls/ACL_UUID",
            match=[
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
            ],
            json={
                "data": {
                    "id": "ACL_UUID",
                    "name": "AA ACL test",
                    "description": "Access list managed by aa-wanderer for the map test. Do not manually edit.",
                    "members": [
                        {
                            "id": "072d2059-5e30-4323-ab5b-2ee3d0bf3466",
                            "name": "Feh'dow Rokym",
                            "inserted_at": "2025-03-03T22:09:15.242731Z",
                            "updated_at": "2025-03-03T22:09:15.242731Z",
                            "role": "viewer",
                            "eve_character_id": "2116864032",
                        },
                        {
                            "id": "b6dba477-b74d-48ee-9de8-caf3dd159605",
                            "name": "Tyd Drakken",
                            "inserted_at": "2025-03-03T22:23:14.736920Z",
                            "updated_at": "2025-03-03T22:23:14.736920Z",
                            "role": "viewer",
                            "eve_character_id": "626646627",
                        },
                        {
                            "id": "e72ea6d7-65cc-4eae-85b5-c43d060084e8",
                            "name": "T'rahk Rokym",
                            "inserted_at": "2025-03-03T22:35:31.149913Z",
                            "updated_at": "2025-03-03T22:35:31.149913Z",
                            "role": "viewer",
                            "eve_character_id": "2112073677",
                        },
                    ],
                    "inserted_at": "2025-03-03T21:07:29.784792Z",
                    "updated_at": "2025-03-03T21:07:29.784792Z",
                    "api_key": "bad-api-key",
                    "owner_id": "aa49f1b7-35de-4fee-9a9a-8165d52ca8bc",
                }
            },
        )

        characters_on_acl = get_acl_member_ids(
            "http://wanderer.localhost", "ACL_UUID", "bad-api-key"
        )

        self.assertIn(2116864032, characters_on_acl)
        self.assertIn(626646627, characters_on_acl)
        self.assertIn(2112073677, characters_on_acl)

    @responses.activate
    def test_get_characters_ids_when_corporation(self):
        """
        Corporation will return a null value in the eve_character_id field
        TODO this null value is a bug and should be fixed at some point
        """
        responses.get(
            "http://wanderer.localhost/api/acls/ACL_UUID",
            match=[
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
            ],
            json={
                "data": {
                    "id": "ACL_UUID",
                    "name": "AA ACL test",
                    "description": "Access list managed by aa-wanderer for the map test. Do not manually edit.",
                    "members": [
                        {
                            "id": "072d2059-5e30-4323-ab5b-2ee3d0bf3466",
                            "name": "Feh'dow Rokym",
                            "inserted_at": "2025-03-03T22:09:15.242731Z",
                            "updated_at": "2025-03-03T22:09:15.242731Z",
                            "role": "viewer",
                            "eve_character_id": "2116864032",
                        },
                        {
                            "id": "b6dba477-b74d-48ee-9de8-caf3dd159605",
                            "name": "Tyd Drakken",
                            "inserted_at": "2025-03-03T22:23:14.736920Z",
                            "updated_at": "2025-03-03T22:23:14.736920Z",
                            "role": "viewer",
                            "eve_character_id": "626646627",
                        },
                        {
                            "id": "e72ea6d7-65cc-4eae-85b5-c43d060084e8",
                            "name": "T'rahk Rokym",
                            "inserted_at": "2025-03-03T22:35:31.149913Z",
                            "updated_at": "2025-03-03T22:35:31.149913Z",
                            "role": "viewer",
                            "eve_character_id": "2112073677",
                        },
                        {
                            "id": "f96069d3-daad-423f-8b9e-f3973871365f",
                            "name": "Rokym's managment organisation",
                            "inserted_at": "2025-03-03T22:47:27.404057Z",
                            "updated_at": "2025-03-03T22:47:27.404057Z",
                            "role": "viewer",
                            "eve_character_id": None,
                        },
                    ],
                    "inserted_at": "2025-03-03T21:07:29.784792Z",
                    "updated_at": "2025-03-03T21:07:29.784792Z",
                    "api_key": "bad-api-key",
                    "owner_id": "aa49f1b7-35de-4fee-9a9a-8165d52ca8bc",
                }
            },
        )

        characters_on_acl = get_acl_member_ids(
            "http://wanderer.localhost", "ACL_UUID", "bad-api-key"
        )

        self.assertIn(2116864032, characters_on_acl)
        self.assertIn(626646627, characters_on_acl)
        self.assertIn(2112073677, characters_on_acl)

    @responses.activate
    def test_add_character_to_access_list(self):
        responses.post(
            "http://wanderer.localhost/api/acls/ACL_UUID/members",
            match=[
                matchers.json_params_matcher(
                    {
                        "member": {
                            "eve_character_id": "2112073677",
                            "role": "member",
                        }
                    }
                ),
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
            ],
            json={
                "data": {
                    "id": "4b143d10-1232-4ac8-a909-46276a4a6064",
                    "name": "T'rahk Rokym",
                    "inserted_at": "2025-03-03T22:29:53.334988Z",
                    "updated_at": "2025-03-03T22:29:53.334988Z",
                    "role": "member",
                    "eve_character_id": "2112073677",
                }
            },
        )

        add_character_to_acl(
            "http://wanderer.localhost", "ACL_UUID", "bad-api-key", 2112073677
        )

    @responses.activate
    def test_remove_member_from_access_list(self):
        responses.delete(
            "http://wanderer.localhost/api/acls/ACL_UUID/members/1000",
            match=[
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
            ],
            json={
                "ok": "true",
            },
        )

        remove_member_from_access_list(
            "http://wanderer.localhost", "ACL_UUID", "bad-api-key", 1000
        )

    @responses.activate
    def test_remove_member_not_on_access_list(self):
        responses.delete(
            "http://wanderer.localhost/api/acls/ACL_UUID/members/1000",
            match=[
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
            ],
            status=404,
            json={"error": "Membership not found for given ACL and external id"},
        )

        self.assertRaises(
            NotFoundError,
            remove_member_from_access_list,
            "http://wanderer.localhost",
            "ACL_UUID",
            "bad-api-key",
            1000,
        )

    @responses.activate
    def test_unknown_owner_eve_id(self):
        """Error will be returned if an unknown owner_eve_id is given when creating an access list"""
        responses.post(
            "http://wanderer.localhost/api/map/acls?slug=map_slug",
            match=[
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
            ],
            status=400,
            json={
                "error": '{:error, "owner_eve_id does not match any existing character"}'
            },
        )

        self.assertRaises(
            OwnerEveIdDoesNotExistError,
            create_acl_associated_to_map,
            "http://wanderer.localhost",
            "map_slug",
            1001,
            "bad-api-key",
        )

    @responses.activate
    def test_get_non_member_characters(self):
        responses.get(
            "http://wanderer.localhost/api/acls/ACL_UUID",
            match=[
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
            ],
            json={
                "data": {
                    "id": "3ed5339a-ad4b-423f-ae44-acbda1b89fe1",
                    "name": "AA ACL quick",
                    "description": "Access list managed by aa-wanderer for the map quick. Do not manually edit.",
                    "members": [
                        {
                            "id": "965a45fd-fe9d-4473-aa41-64d92df26b6a",
                            "name": "Feh'dow Rokym",
                            "inserted_at": "2025-03-04T22:29:33.549264Z",
                            "updated_at": "2025-03-04T22:29:33.549264Z",
                            "role": "viewer",
                            "eve_character_id": "2116864032",
                        },
                        {
                            "id": "02c32352-72f8-4f88-b9ac-073fefdfb88f",
                            "name": "T'rahk Rokym",
                            "inserted_at": "2025-03-04T22:29:36.457675Z",
                            "updated_at": "2025-03-04T22:29:44.022579Z",
                            "role": "manager",
                            "eve_character_id": "2112073677",
                        },
                        {
                            "id": "13fcef47-0c1a-4165-af72-d81af4afec58",
                            "name": "Dkw'sks Rokym",
                            "inserted_at": "2025-03-04T22:29:41.226575Z",
                            "updated_at": "2025-03-04T22:29:53.636615Z",
                            "role": "admin",
                            "eve_character_id": "2116461863",
                        },
                        {
                            "id": "efa8a772-aaa4-41ac-b24a-a1857db0a358",
                            "name": "Rokym's managment organisation",
                            "inserted_at": "2025-03-04T22:41:04.620362Z",
                            "updated_at": "2025-03-04T22:41:04.620362Z",
                            "role": "viewer",
                            "eve_character_id": None,
                        },
                    ],
                    "inserted_at": "2025-03-04T21:05:21.902253Z",
                    "updated_at": "2025-03-04T21:05:21.902253Z",
                    "api_key": "447c56d3-3ca1-4224-a961-ec7871a111e6",
                    "owner_id": "aa49f1b7-35de-4fee-9a9a-8165d52ca8bc",
                }
            },
        )

        non_members_ids = get_non_member_characters(
            "http://wanderer.localhost", "ACL_UUID", "bad-api-key"
        )

        self.assertIn((2112073677, AccessListRoles.MANAGER), non_members_ids)
        self.assertIn((2116461863, AccessListRoles.ADMIN), non_members_ids)

    @responses.activate
    def test_set_character_to_member(self):
        responses.put(
            "http://wanderer.localhost/api/acls/ACL_UUID/members/1001",
            match=[
                matchers.header_matcher({"Authorization": "Bearer bad-api-key"}),
                matchers.json_params_matcher({"member": {"role": "member"}}),
            ],
        )

        set_character_to_member(
            "http://wanderer.localhost", "ACL_UUID", "bad-api-key", 1001
        )
