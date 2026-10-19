"""
Syncing Alliance Auth groups to Astropath ACLs.

Each AstropathACLMapping links an AA Group to an Astropath ACL ID with a role.
Multiple groups can map to the same ACL - their members are merged, with the
highest-privilege role winning when a character appears in more than one group.

Connection details are stored in a single AstropathConfiguration row in the DB,
managed via the Django admin.
"""

import time

import requests
from django.contrib.auth.models import User

from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)

TIMEOUT = 30

_ROLE_RANK = {"viewer": 0, "editor": 1, "admin": 2}


class AstropathNotConfiguredError(Exception):
    """Raised when no AstropathConfiguration row exists in the database."""


class AstropathConflictError(Exception):
    """Raised when a PUT /entries returns 409 (stale revision)."""


def _settings() -> tuple[str, str]:
    from wanderer.models import AstropathConfiguration

    config = AstropathConfiguration.objects.first()
    if config is None:
        raise AstropathNotConfiguredError(
            "Create an Astropath Configuration in the admin before syncing."
        )
    return config.url.rstrip("/"), config.api_key


def list_acls() -> list[dict]:
    """Fetch all access lists visible to the API key.

    Returns a list of dicts with at least ``id`` (int) and ``name`` (str).
    Raises AstropathNotConfiguredError if no configuration row exists,
    or requests.HTTPError on a non-2xx response.
    """
    url, key = _settings()
    r = requests.get(
        f"{url}/external/v1/access-lists",
        headers={"Authorization": f"Bearer {key}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    return r.json()["lists"]


def get_acl_entries(url: str, key: str, acl_id: int) -> tuple[int, list[dict]]:
    """
    Fetches the current entries for an ACL.
    Returns (revision, entries).
    """
    r = requests.get(
        f"{url}/external/v1/access-lists/{acl_id}/entries",
        headers={"Authorization": f"Bearer {key}"},
        timeout=TIMEOUT,
    )
    r.raise_for_status()
    data = r.json()
    return data["revision"], data.get("entries", [])


def replace_acl_entries(
    url: str, key: str, acl_id: int, revision: int, entries: list[dict]
) -> dict:
    """
    Replaces all entries on an ACL with the given list.
    Returns the SyncResult dict from Astropath.
    Raises AstropathConflictError on 409 (stale revision - caller should retry).
    """
    r = requests.put(
        f"{url}/external/v1/access-lists/{acl_id}/entries",
        json={"revision": revision, "entries": entries},
        headers={"Authorization": f"Bearer {key}"},
        timeout=TIMEOUT,
    )
    if r.status_code == 409:
        raise AstropathConflictError(f"Stale revision {revision} for ACL {acl_id}")
    if not r.ok:
        logger.error(
            "Astropath PUT /access-lists/%d/entries returned %d: %s",
            acl_id, r.status_code, r.text,
        )
    r.raise_for_status()
    return r.json()


def _build_entries(group_roles: list[tuple[int, str]]) -> list[dict]:
    """
    Builds the full entry list for an ACL from a list of (group_id, role) pairs.

    Only each user's main character is included. When a user belongs to multiple
    groups with different roles, the highest-privilege role wins.
    """
    char_roles: dict[int, str] = {}

    for group_id, role in group_roles:
        users = User.objects.filter(groups__id=group_id).select_related(
            "profile__main_character"
        ).distinct()
        for user in users:
            main = user.profile.main_character
            if main is None:
                continue
            char_id = main.character_id
            existing_rank = _ROLE_RANK.get(char_roles.get(char_id, ""), -1)
            if _ROLE_RANK.get(role, 0) > existing_rank:
                char_roles[char_id] = role

    return [
        {"subjectType": "character", "subjectId": char_id, "role": role}
        for char_id, role in char_roles.items()
    ]


def sync_acl(acl_id: int, group_roles: list[tuple[int, str]]) -> dict:
    """
    Syncs a single Astropath ACL to match the members of the mapped groups.

    group_roles: list of (group_id, role) pairs for this ACL.
    Returns the SyncResult dict from Astropath, or {} if a newer sync already ran.

    The revision is a client-supplied monotonically increasing value — the contract
    requires it to be strictly greater than the last stored revision (see
    contracts/external-v1.yaml). We use the current time in milliseconds, which
    satisfies this without needing a prior GET. A 409 means another process synced
    more recently, so our data is already superseded — we skip rather than retry.
    """
    url, key = _settings()
    entries = _build_entries(group_roles)
    revision = int(time.time() * 1000)
    try:
        result = replace_acl_entries(url, key, acl_id, revision, entries)
    except AstropathConflictError:
        logger.info(
            "ACL %d already synced with a newer revision, skipping", acl_id
        )
        return {}
    logger.info(
        "Synced ACL %d: %d entries, +%d -%d ~%d",
        acl_id,
        result.get("entryCount", 0),
        result.get("added", 0),
        result.get("removed", 0),
        result.get("changed", 0),
    )
    return result
