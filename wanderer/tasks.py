"""Tasks."""

from celery import chain, shared_task

from allianceauth.services.hooks import get_extension_logger

from wanderer.models import MapStructure, WandererAccount, WandererManagedMap
from wanderer.wanderer import AccessListRoles, get_map_structures

logger = get_extension_logger(__name__)


@shared_task
def add_alts_to_map(wanderer_user_id: int, wanderer_managed_map_id: int):
    """
    Ensures that all alts of this user are properly added on the wanderer map ACL.
    """
    logger.info(
        "Updating character of user id %d on map id %d",
        wanderer_user_id,
        wanderer_managed_map_id,
    )

    wanderer_user = WandererAccount.objects.get(pk=wanderer_user_id)
    wanderer_managed_map = WandererManagedMap.objects.get(pk=wanderer_managed_map_id)

    logger.debug("Recovered user %s and map %s", wanderer_user, wanderer_managed_map)

    characters_on_acl_ids_set = set(
        wanderer_managed_map.get_character_ids_on_access_list()
    )
    logger.debug(characters_on_acl_ids_set)
    user_character_ids_set = set(wanderer_user.get_all_character_ids())
    logger.debug(user_character_ids_set)

    missing_characters_set = user_character_ids_set - characters_on_acl_ids_set
    logger.info(
        "Need to add %d characters to the access list", len(missing_characters_set)
    )
    logger.debug(missing_characters_set)

    for missing_character_id in missing_characters_set:
        logger.debug("Adding character id %d to the access list", missing_character_id)
        wanderer_managed_map.add_character_to_acl(missing_character_id)


@shared_task
def remove_user_characters_from_map(
    wanderer_user_id: int, wanderer_managed_map_id: int
):
    """
    Removes all characters from that specific user from the map
    """
    logger.info(
        "Removing all characters of user id %d from map id %d",
        wanderer_user_id,
        wanderer_managed_map_id,
    )

    wanderer_user = WandererAccount.objects.get(pk=wanderer_user_id)
    wanderer_managed_map = WandererManagedMap.objects.get(pk=wanderer_managed_map_id)
    logger.debug(wanderer_user, wanderer_managed_map)

    characters_on_acl_ids_set = set(
        wanderer_managed_map.get_character_ids_on_access_list()
    )
    logger.debug(characters_on_acl_ids_set)
    user_character_ids_set = set(wanderer_user.get_all_character_ids())
    logger.debug(user_character_ids_set)

    character_ids_to_remove = characters_on_acl_ids_set & user_character_ids_set

    for character_id_to_remove in character_ids_to_remove:
        logger.debug(
            "Removing char id %d from map %s",
            character_id_to_remove,
            wanderer_managed_map,
        )
        wanderer_managed_map.remove_member_from_access_list(character_id_to_remove)


@shared_task
def cleanup_access_list(wanderer_managed_map_id: int):
    """
    Removes all unwanted members and add missing alts from the map's access list
    """
    logger.info("Updating access list of map id %d", wanderer_managed_map_id)

    wanderer_managed_map = WandererManagedMap.objects.get(pk=wanderer_managed_map_id)

    characters_on_acl_ids_set = set(
        wanderer_managed_map.get_character_ids_on_access_list()
    )
    logger.debug(characters_on_acl_ids_set)
    characters_that_should_be_on_acls_ids_set = set(
        wanderer_managed_map.get_all_accounts_characters_ids()
    )
    logger.debug(characters_that_should_be_on_acls_ids_set)

    character_ids_to_remove = (
        characters_on_acl_ids_set - characters_that_should_be_on_acls_ids_set
    )
    logger.debug(character_ids_to_remove)
    logger.info("Removing %d character ids from the ACL", len(character_ids_to_remove))
    for character_id_to_remove in character_ids_to_remove:
        logger.debug("Removing char id %d", character_id_to_remove)
        wanderer_managed_map.remove_member_from_access_list(character_id_to_remove)

    character_ids_to_add = (
        characters_that_should_be_on_acls_ids_set - characters_on_acl_ids_set
    )
    logger.debug(character_ids_to_add)
    logger.info("Adding %d character ids to the ACL", len(character_ids_to_add))
    for character_id_to_add in character_ids_to_add:
        logger.debug("Adding character id %d", character_id_to_add)
        wanderer_managed_map.add_character_to_acl(character_id_to_add)

    non_member_characters = wanderer_managed_map.get_non_member_characters()
    character_ids_to_set_on_member = [
        non_member_character[0]
        for non_member_character in non_member_characters
        if non_member_character[1]
        not in [AccessListRoles.ADMIN, AccessListRoles.MANAGER, AccessListRoles.MEMBER]
    ]
    for character_id_to_set_on_member in character_ids_to_set_on_member:
        wanderer_managed_map.set_character_to_member(character_id_to_set_on_member)


@shared_task
def sync_map_structures(wanderer_managed_map_id: int):
    """Fetch structures from Wanderer and upsert them into the local DB."""
    logger.info("Syncing structures for map id %d", wanderer_managed_map_id)

    wanderer_map = WandererManagedMap.objects.get(pk=wanderer_managed_map_id)
    structures = get_map_structures(
        wanderer_map.wanderer_url, wanderer_map.map_slug, wanderer_map.map_api_key
    )

    seen_ids = set()
    for s in structures:
        wanderer_id = s["id"]
        seen_ids.add(wanderer_id)
        MapStructure.objects.update_or_create(
            wanderer_id=wanderer_id,
            defaults={
                "map": wanderer_map,
                "name": s.get("name", ""),
                "structure_type": s.get("structure_type", ""),
                "structure_type_id": s.get("structure_type_id", ""),
                "solar_system_id": s.get("solar_system_id"),
                "solar_system_name": s.get("solar_system_name", ""),
                "owner_name": s.get("owner_name", ""),
                "owner_ticker": s.get("owner_ticker", ""),
                "status": s.get("status", ""),
                "end_time": s.get("end_time"),
                "notes": s.get("notes", ""),
            },
        )

    deleted, _ = MapStructure.objects.filter(map=wanderer_map).exclude(
        wanderer_id__in=seen_ids
    ).delete()
    logger.info(
        "Map %d: upserted %d structures, deleted %d stale entries",
        wanderer_managed_map_id,
        len(seen_ids),
        deleted,
    )


@shared_task
def sync_all_map_structures():
    """Hourly task: sync structures for all maps that have sync enabled."""
    maps = WandererManagedMap.objects.filter(sync_structures=True)
    logger.info("%d maps with structure sync enabled", maps.count())
    tasks = [sync_map_structures.si(m.id) for m in maps]
    if tasks:
        chain(tasks).delay()


@shared_task
def cleanup_all_access_lists():
    """
    Periodically cycle through all access lists to clean up unwanted members and add missing alts
    """
    logger.info("Starting a cleanup of all access lists")

    wanderer_managed_maps = WandererManagedMap.objects.all()

    logger.info("%d maps to cleanup", wanderer_managed_maps.count())

    tasks = [
        cleanup_access_list.si(wanderer_managed_map.id)
        for wanderer_managed_map in wanderer_managed_maps
    ]

    chain(tasks).delay()
