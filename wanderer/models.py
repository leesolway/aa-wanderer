"""Models."""

from typing import Optional

from django.conf import settings
from django.contrib.auth.models import Group, User
from django.db import models
from django.utils.translation import gettext_lazy as _

from allianceauth.authentication.models import State
from allianceauth.eveonline.models import (
    EveAllianceInfo,
    EveCharacter,
    EveCorporationInfo,
    EveFactionInfo,
)
from allianceauth.framework.api.user import get_all_characters_from_user
from allianceauth.services.hooks import get_extension_logger

from wanderer.managers import WandererManagedMapManager
from wanderer.wanderer import (
    NotFoundError,
    add_character_to_acl,
    get_acl_members,
    remove_member_from_access_list,
)

logger = get_extension_logger(__name__)


class General(models.Model):
    """A metamodel for app permissions."""

    class Meta:
        managed = False
        default_permissions = ()
        permissions = (("basic_access", "Can access this app"),)


class WandererManagedMap(models.Model):
    """Wanderer map with an ACL managed by the auth"""

    objects = WandererManagedMapManager()

    name = models.CharField(
        max_length=80,
        help_text=_("User friendly name for your users to recognize the map"),
    )
    wanderer_url = models.CharField(
        max_length=120, help_text=_("URL of the wanderer instance")
    )
    map_slug = models.CharField(
        max_length=20, help_text=_("Map slug on the wanderer instance")
    )
    map_api_key = models.CharField(max_length=100, help_text=_("API key of the map"))

    map_acl_id = models.CharField(
        max_length=100, help_text=_("ID of the managed access list")
    )
    map_acl_api_key = models.CharField(
        max_length=100, help_text=_("API key of the managed access list")
    )

    state_access = models.ManyToManyField(
        State, blank=True, help_text=_("States to whose members this map is available.")
    )

    group_access = models.ManyToManyField(
        Group, blank=True, help_text=_("Groups to whose members this map is available.")
    )

    character_access = models.ManyToManyField(
        EveCharacter,
        blank=True,
        help_text=_("Characters to which this map is available."),
    )

    corporation_access = models.ManyToManyField(
        EveCorporationInfo,
        blank=True,
        help_text=_("Corporations to whose members this map is available."),
    )

    alliance_access = models.ManyToManyField(
        EveAllianceInfo,
        blank=True,
        help_text=_("Alliances to whose members this map is available."),
    )

    faction_access = models.ManyToManyField(
        EveFactionInfo,
        blank=True,
        help_text=_("Factions to whose members this map is available."),
    )

    def __str__(self):
        return f"{self.wanderer_url}/{self.map_slug}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["wanderer_url", "map_slug"], name="functional_pk_urlslug"
            )
        ]

    def accessible_by(self, user: User) -> bool:
        """Defines if a user can access this map or not"""

        logger.debug("Checking if user %s can access the map %s", user, self.name)

        if not user.has_perm("wanderer.basic_access"):
            return False

        try:
            main_character: EveCharacter = user.profile.main_character
            assert main_character

            if user.is_superuser:
                logger.info("Returning all servers to user %s", user)
                return True

            # build queries then OR them all
            queries = []

            # States access everyone has a state
            queries.append(models.Q(state_access=user.profile.state))
            # Groups access, is ok if no groups.
            queries.append(models.Q(group_access__in=user.groups.all()))
            # ONLY on main char from here down
            # Character access
            queries.append(models.Q(character_access=main_character))
            # Corp access
            try:
                queries.append(
                    models.Q(
                        corporation_access=EveCorporationInfo.objects.get(
                            corporation_id=main_character.corporation_id
                        )
                    )
                )
            except EveCorporationInfo.DoesNotExist:
                pass
            # Alliance access if part of an alliance
            try:
                if main_character.alliance_id:
                    queries.append(
                        models.Q(
                            alliance_access=EveAllianceInfo.objects.get(
                                alliance_id=main_character.alliance_id
                            )
                        )
                    )
            except EveAllianceInfo.DoesNotExist:
                pass
            # Faction access if part of a faction
            try:
                if main_character.faction_id:
                    queries.append(
                        models.Q(
                            faction_access=EveFactionInfo.objects.get(
                                faction_id=main_character.faction_id
                            )
                        )
                    )
            except EveFactionInfo.DoesNotExist:
                pass

            logger.debug(
                "%d queries for %s 's visible characters", len(queries), main_character
            )

            if settings.DEBUG:
                logger.debug(queries)

            # filter based on "OR" all queries
            query = queries.pop()
            for q in queries:
                query |= q
            return WandererManagedMap.objects.filter(query, id=self.id).exists()

        except AssertionError:
            logger.info("User %s without eve character can't access maps", user)
            return False

    def user_has_account(self, user: User) -> bool:
        """Return true if the user has an active account on this map"""
        return WandererAccount.objects.filter(user=user, wanderer_map=self).exists()

    def get_user_account(self, user: User) -> Optional["WandererAccount"]:
        """Returns the user account associated to this map if it exists"""
        try:
            return WandererAccount.objects.get(user=user, wanderer_map=self)
        except WandererAccount.DoesNotExist:
            return None

    def delete_user(self, user: User):
        """Removes the user characters from the map and then deletes the associated account"""
        wanderer_account = self.get_user_account(user)
        for character_to_remove_id in wanderer_account.get_all_character_ids():
            try:
                self.remove_member_from_access_list(character_to_remove_id)
            except (
                NotFoundError
            ):  # If the character is already off the access list we're good
                pass
        wanderer_account.delete()

    def get_character_ids_on_access_list(self) -> list[int]:
        """Returns all character_ids present on the access list"""
        return get_acl_members(self.wanderer_url, self.map_acl_id, self.map_acl_api_key)

    def add_character_to_acl(self, character_id: int):
        """Adds a single character to the ACL with the viewer role"""
        return add_character_to_acl(
            self.wanderer_url, self.map_acl_id, self.map_acl_api_key, character_id
        )

    def remove_member_from_access_list(self, member_id: int):
        """
        Removes a member from the access list.
        member_id can be character/corporation/alliance.
        """

        return remove_member_from_access_list(
            self.wanderer_url, self.map_acl_id, self.map_acl_api_key, member_id
        )

    def get_all_accounts_characters_ids(self) -> list[int]:
        """
        Returns a list of all character ids of accounts linked to this map
        """
        return list(
            self.accounts.values_list(
                "user__character_ownerships__character__character_id", flat=True
            )
        )


class WandererAccount(models.Model):
    """Represents a user linked to a wanderer map"""

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, help_text=_("Auth user linked to the map")
    )
    wanderer_map = models.ForeignKey(
        WandererManagedMap,
        models.CASCADE,
        related_name="accounts",
        related_query_name="account",
        help_text=_("Wanderer map to which the user is linked"),
    )

    def __str__(self):
        return f"{self.user} - {self.wanderer_map}"

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "wanderer_map"], name="functional_pk_user_map"
            )
        ]

    def get_all_character_ids(self) -> list[int]:
        """Return all character ids associated to this account"""
        return [
            character.character_id
            for character in get_all_characters_from_user(self.user)
        ]
