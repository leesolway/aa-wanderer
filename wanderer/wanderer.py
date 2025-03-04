"""Interactions with the wanderer's API"""

import requests

from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)


class BadAPIKeyError(Exception):
    """Exception raised when a wrong API key is provided"""


class NotFoundError(Exception):
    """Exception raised when the API returned an expected 404"""


DEFAULT_TIMEOUT = 5


def create_acl_associated_to_map(
    wanderer_url: str, map_slug: str, requesting_character: int, map_api_key: str
) -> (str, str):
    """
    Will create a new ACL associated with the map `map_slug`

    Returns the ACL associated id and API key
    """

    logger.info(
        "Creating ACL on wanderer %s for map %s by character %d with api key %s",
        wanderer_url,
        map_slug,
        requesting_character,
        map_api_key,
    )

    r = requests.post(
        f"{wanderer_url}/api/map/acls?slug={map_slug}",
        headers={"Authorization": f"Bearer {map_api_key}"},
        json={
            "acl": {
                "name": f"AA ACL {map_slug}",
                "description": f"Access list managed by aa-wanderer for the map {map_slug}. Do not manually edit.",
                "owner_eve_id": str(requesting_character),
            }
        },
        timeout=DEFAULT_TIMEOUT,
    )

    logger.debug("Received status code %d", r.status_code)

    if r.status_code == 401:
        raise BadAPIKeyError(
            f"The API key {map_api_key} returned a 401 when trying to create an ACL on map {wanderer_url} {map_slug}"
        )

    r.raise_for_status()

    acl_id = r.json()["data"]["id"]
    acl_key = r.json()["data"]["api_key"]
    logger.info("Successfully created ACL id %s")

    return acl_id, acl_key


def get_acl_members(wanderer_url: str, acl_id: str, acl_api_key: str) -> list[int]:
    """
    Returns all members eve_character_id present in an ACL
    """
    logger.info("Requesting character on the ACL of map %s / %s", wanderer_url, acl_id)

    r = requests.get(
        f"{wanderer_url}/api/acls/{acl_id}",
        headers={"Authorization": f"Bearer {acl_api_key}"},
        timeout=DEFAULT_TIMEOUT,
    )
    logger.debug(r)
    logger.debug(r.text)

    if r.status_code == 401:
        raise BadAPIKeyError(
            f"The API key {acl_api_key} returned a 401 when trying to access the members of ACL {wanderer_url} {acl_id}"
        )

    r.raise_for_status()

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

    r = requests.post(
        f"{wanderer_url}/api/acls/{acl_id}/members",
        headers={"Authorization": f"Bearer {acl_api_key}"},
        json={
            "member": {
                "eve_character_id": str(character_id),
                "role": "viewer",
            }
        },
        timeout=DEFAULT_TIMEOUT,
    )

    if r.status_code == 401:
        raise BadAPIKeyError(
            f"The API key {acl_api_key} returned a 401 when trying to access the members of ACL {wanderer_url} {acl_id}"
        )

    r.raise_for_status()


def remove_member_from_access_list(
    wanderer_url: str, acl_id: str, acl_api_key: str, member_id: int
):
    """
    Removes the member with specified id from the ACL
    """

    r = requests.delete(
        f"{wanderer_url}/api/acls/{acl_id}/members/{member_id}",
        headers={"Authorization": f"Bearer {acl_api_key}"},
        timeout=DEFAULT_TIMEOUT,
    )

    if r.status_code == 401:
        raise BadAPIKeyError(
            f"The API key {acl_api_key} returned a 401 when trying to access the members of ACL {wanderer_url} {acl_id}"
        )

    if r.status_code == 404:  # If the API isn't found a 401 is raised
        raise NotFoundError(f"Member id {member_id} was not found on ACL {acl_id}")

    r.raise_for_status()
