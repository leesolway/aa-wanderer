"""Interactions with the wanderer's API"""

import enum

from requests import HTTPError

from allianceauth.services.hooks import get_extension_logger

from wanderer.utils import req

logger = get_extension_logger(__name__)


class AccessListRoles(enum.Enum):
    """All roles that can be assigned on an access list"""

    ADMIN = "admin"
    MANAGER = "manager"
    MEMBER = "member"
    VIEWER = "viewer"
    BLOCKED = "-blocked-"


class NotFoundError(Exception):
    """Exception raised when the API returned an expected 404"""


class OwnerEveIdDoesNotExistError(Exception):
    """Exception raised when attempting to create a map with an owner not known by Wanderer"""


DEFAULT_TIMEOUT = 5


def create_acl_associated_to_map(
    wanderer_url: str, map_slug: str, requesting_character_id: int, map_api_key: str
) -> tuple[str, str]:
    """
    Will create a new ACL associated with the map `map_slug`

    Returns the ACL associated id and API key
    """

    logger.info(
        "Creating ACL on wanderer %s for map %s by character %d with api key %s",
        wanderer_url,
        map_slug,
        requesting_character_id,
        map_api_key,
    )

    try:
        r = req.post(
            wanderer_url,
            f"map/acls?slug={map_slug}",
            bearer_token=map_api_key,
            json={
                "acl": {
                    "name": f"AA ACL {map_slug}",
                    "description": f"Access list managed by aa-wanderer for the map {map_slug}. Do not manually edit.",
                    "owner_eve_id": str(requesting_character_id),
                }
            },
        )
    except HTTPError as e:
        if (
            e.response.status_code == 400
            and "owner_eve_id does not match any existing character" in e.response.text
        ):
            raise OwnerEveIdDoesNotExistError(
                f"The eve character with id {requesting_character_id} "
                "doesn't seem to be known by Wanderer"
            ) from e

        raise

    acl_id = r.json()["data"]["id"]
    acl_key = r.json()["data"]["api_key"]
    logger.info("Successfully created ACL id %s")

    return acl_id, acl_key


def get_acl_member_ids(wanderer_url: str, acl_id: str, acl_api_key: str) -> list[int]:
    """
    Returns all members eve_character_id present in an ACL
    """
    logger.info("Requesting character on the ACL of map %s / %s", wanderer_url, acl_id)

    r = _get_raw_acl_members(wanderer_url, acl_id, acl_api_key)

    return [
        int(member["eve_character_id"])
        for member in r.json()["data"]["members"]
        if member["eve_character_id"]
    ]


def add_character_to_acl(
    wanderer_url: str, acl_id: str, acl_api_key: str, character_id: int
):
    """
    Adds a single character to the ACL with the viewer role
    """

    req.post(
        wanderer_url,
        f"acls/{acl_id}/members",
        bearer_token=acl_api_key,
        json={
            "member": {
                "eve_character_id": str(character_id),
                "role": "member",
            }
        },
    )


def remove_member_from_access_list(
    wanderer_url: str, acl_id: str, acl_api_key: str, member_id: int
):
    """
    Removes the member with specified id from the ACL
    """

    try:
        req.delete(
            wanderer_url,
            f"acls/{acl_id}/members/{member_id}",
            bearer_token=acl_api_key,
        )
    except HTTPError as e:
        if e.response.status_code == 404:  # If the API isn't found a 401 is raised
            raise NotFoundError(
                f"Member id {member_id} was not found on ACL {acl_id}"
            ) from e
        raise


def get_non_member_characters(
    wanderer_url: str, acl_id: str, acl_api_key: str
) -> list[tuple[int, AccessListRoles]]:
    """
    Return the character_id and role of characters that have a role different from member
    """
    logger.info(
        "Requesting character on the ACL of map %s / %s without member role",
        wanderer_url,
        acl_id,
    )

    r = _get_raw_acl_members(wanderer_url, acl_id, acl_api_key)

    return [
        (int(member["eve_character_id"]), AccessListRoles(member["role"]))
        for member in r.json()["data"]["members"]
        if member["role"] != "member" and member["eve_character_id"]
    ]


def set_character_to_member(
    wanderer_url: str, acl_id: str, acl_api_key: str, character_id
):
    """
    Sets the character with the given eve id to member on the access list
    """
    logger.info(
        "Making character %d to member on map %s / %s",
        character_id,
        wanderer_url,
        acl_id,
    )

    req.put(
        wanderer_url,
        f"acls/{acl_id}/members/{character_id}",
        bearer_token=acl_api_key,
        json={
            "member": {
                "role": "member",
            }
        },
    )


def get_map_structures(wanderer_url: str, map_slug: str, map_api_key: str) -> list[dict]:
    """Returns all structures for a given map."""
    r = req.get(
        wanderer_url,
        f"maps/{map_slug}/structures",
        bearer_token=map_api_key,
    )
    return r.json()["data"]


def _get_raw_acl_members(wanderer_url: str, acl_id: str, acl_api_key: str):
    """Returns the raw result of requesting the members on an access list"""
    r = req.get(
        wanderer_url,
        f"acls/{acl_id}",
        bearer_token=acl_api_key,
    )

    return r
