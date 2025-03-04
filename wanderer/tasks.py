"""Tasks."""

from celery import chain, shared_task

from allianceauth.services.hooks import get_extension_logger

from wanderer.models import WandererAccount, WandererManagedMap

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
