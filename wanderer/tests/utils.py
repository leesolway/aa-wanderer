from allianceauth.authentication.models import CharacterOwnership
from allianceauth.eveonline.models import EveCharacter
from app_utils.testing import create_fake_user

from wanderer.models import WandererAccount, WandererManagedMap


def create_managed_map() -> WandererManagedMap:
    """Create a basic for testing"""
    return WandererManagedMap.objects.create(
        wanderer_url="http://wanderer.localhost",
        map_slug="test",
        map_api_key="bad-map-api-key",
        map_acl_id="ACL_UUID",
        map_acl_api_key="bad-acl-api-key",
    )


def create_wanderer_users(
    wanderer_managed_map: WandererManagedMap, count=1
) -> list[WandererAccount]:
    """
    Create fake users linked to a map and character ownerships associated
    """
    users = []
    for i in range(count):
        user = create_fake_user(
            character_name=f"fake character {i}",
            character_id=1000 + i,
            corporation_id=2000 + i,
            corporation_name=f"fake corporation {i}",
            corporation_ticker=f"FAKE{i}",
        )
        users.append(
            WandererAccount.objects.create(user=user, wanderer_map=wanderer_managed_map)
        )

        for j in range(2):
            eve_character, _ = EveCharacter.objects.get_or_create(
                character_id=1000 + 10 * j + i,
                character_name=f"fake character {10*j+i}",
                corporation_id=2000 + i,
                corporation_name=f"fake corporation {i}",
                corporation_ticker=f"FAKE{i}",
            )
            char_ownership, _ = CharacterOwnership.objects.get_or_create(
                character=eve_character, user=user, owner_hash=f"fake hash {10*j+i}"
            )

    return users
