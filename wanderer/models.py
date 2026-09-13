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
    AccessListRoles,
    NotFoundError,
    add_character_to_acl,
    get_acl_member_ids,
    get_non_member_characters,
    remove_member_from_access_list,
    set_character_to_member,
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

    sync_structures = models.BooleanField(
        default=False,
        help_text=_("Enable hourly structure sync for this map"),
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

        main_character: EveCharacter = user.profile.main_character
        if not main_character:
            logger.info("User %s without eve character can't access maps", user)
            return False

        if user.is_superuser:
            logger.info("Returning all servers to user %s", user)
            return True

        # Build queries then OR them all. Use cross-relation lookups on the character's
        # IDs directly — no extra DB queries to fetch the related model instances first.
        queries = [
            models.Q(state_access=user.profile.state),
            models.Q(group_access__in=user.groups.all()),
            models.Q(character_access=main_character),
            models.Q(corporation_access__corporation_id=main_character.corporation_id),
        ]
        if main_character.alliance_id:
            queries.append(models.Q(alliance_access__alliance_id=main_character.alliance_id))
        if main_character.faction_id:
            queries.append(models.Q(faction_access__faction_id=main_character.faction_id))

        logger.debug("%d queries for %s's visible characters", len(queries), main_character)
        if settings.DEBUG:
            logger.debug(queries)

        query = queries[0]
        for q in queries[1:]:
            query |= q
        return WandererManagedMap.objects.filter(query, id=self.id).exists()

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
        return get_acl_member_ids(
            self.wanderer_url, self.map_acl_id, self.map_acl_api_key
        )

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

    def get_non_member_characters(self) -> list[(int, AccessListRoles)]:
        """
        Return a list of all character ids and roles that are not set as members
        """
        return get_non_member_characters(
            self.wanderer_url, self.map_acl_id, self.map_acl_api_key
        )

    def set_character_to_member(self, character_id: int):
        """
        Sets the given character id to member on the access list
        """
        set_character_to_member(
            self.wanderer_url, self.map_acl_id, self.map_acl_api_key, character_id
        )


class MapStructure(models.Model):
    """A structure synced from a Wanderer map."""

    wanderer_id = models.CharField(max_length=100, unique=True)
    map = models.ForeignKey(
        WandererManagedMap,
        on_delete=models.CASCADE,
        related_name="structures",
    )
    name = models.CharField(max_length=255, blank=True)
    structure_type = models.CharField(max_length=100, blank=True)
    structure_type_id = models.CharField(max_length=50, blank=True)
    solar_system = models.ForeignKey(
        "eve_sde.SolarSystem",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    owner_name = models.CharField(max_length=255, blank=True)
    owner_ticker = models.CharField(max_length=10, blank=True)
    owner_id = models.CharField(max_length=50, blank=True)
    alliance_name = models.CharField(max_length=255, blank=True)
    alliance_ticker = models.CharField(max_length=10, blank=True)
    alliance_id = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=50, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)
    inserted_at = models.DateTimeField(null=True, blank=True)
    structure_updated_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text=_(
            "The 'updated_at' timestamp reported by Wanderer for this structure, "
            "used to decide which source map has the freshest data for a structure "
            "seen on more than one map."
        ),
    )
    is_active = models.BooleanField(default=True)
    removed_at = models.DateTimeField(null=True, blank=True)
    last_synced = models.DateTimeField(auto_now=True)

    def __str__(self):
        solar_system_name = self.solar_system.name if self.solar_system else ""
        return f"{self.name} ({solar_system_name})"

    def freshness(self):
        """Best available timestamp for comparing this row's data against another map's."""
        return self.structure_updated_at or self.inserted_at or self.last_synced

    class Meta:
        ordering = ["map__name", "solar_system__name", "name"]


# Fields tracked on Structure that get diffed/snapshotted by the reconciliation
# process in wanderer/structures.py. Order matters for StructureHistory display.
STRUCTURE_TRACKED_FIELDS = [
    "name",
    "structure_type",
    "structure_type_id",
    "owner_name",
    "owner_ticker",
    "owner_id",
    "alliance_name",
    "alliance_ticker",
    "alliance_id",
    "status",
    "end_time",
    "notes",
]


class Structure(models.Model):
    """
    A real-world structure, deduplicated across every source map.

    Reconciled from MapStructure rows keyed on (solar_system, name, structure_type_id) -
    Wanderer's own structure id is only unique within a single map, so it can't be used
    to recognize the same structure reported by two different maps. See
    wanderer.structures.reconcile_structures().
    """

    solar_system = models.ForeignKey(
        "eve_sde.SolarSystem",
        on_delete=models.CASCADE,
        related_name="+",
    )
    name = models.CharField(max_length=255)
    structure_type = models.CharField(max_length=100, blank=True)
    structure_type_id = models.CharField(max_length=50, blank=True)

    owner_name = models.CharField(max_length=255, blank=True)
    owner_ticker = models.CharField(max_length=10, blank=True)
    owner_id = models.CharField(max_length=50, blank=True)
    alliance_name = models.CharField(max_length=255, blank=True)
    alliance_ticker = models.CharField(max_length=10, blank=True)
    alliance_id = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=50, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    first_seen_at = models.DateTimeField(auto_now_add=True)
    last_seen_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    last_source_map = models.ForeignKey(
        WandererManagedMap,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        help_text=_(
            "Map that most recently supplied this structure's data. Kept for "
            "admin/debugging only - not shown to end users, who shouldn't need to "
            "care which map a structure was seen on."
        ),
    )

    def __str__(self):
        return f"{self.name} ({self.solar_system.name})"

    class Meta:
        ordering = ["solar_system__name", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["solar_system", "name", "structure_type_id"],
                name="functional_pk_structure_identity",
            )
        ]


class StructureHistory(models.Model):
    """
    An archived snapshot of a Structure's fields, recorded right before they
    changed (or right before the structure was marked removed).
    """

    class ChangeType(models.TextChoices):
        CREATED = "created", _("Created")
        UPDATED = "updated", _("Updated")
        REMOVED = "removed", _("Removed")
        REAPPEARED = "reappeared", _("Reappeared")

    structure = models.ForeignKey(
        Structure, on_delete=models.CASCADE, related_name="history"
    )
    recorded_at = models.DateTimeField(auto_now_add=True)
    change_type = models.CharField(max_length=20, choices=ChangeType.choices)
    changed_fields = models.JSONField(default=list, blank=True)

    # Snapshot of the structure's data fields as they were right before this change.
    name = models.CharField(max_length=255, blank=True)
    structure_type = models.CharField(max_length=100, blank=True)
    structure_type_id = models.CharField(max_length=50, blank=True)
    owner_name = models.CharField(max_length=255, blank=True)
    owner_ticker = models.CharField(max_length=10, blank=True)
    owner_id = models.CharField(max_length=50, blank=True)
    alliance_name = models.CharField(max_length=255, blank=True)
    alliance_ticker = models.CharField(max_length=10, blank=True)
    alliance_id = models.CharField(max_length=50, blank=True)
    status = models.CharField(max_length=50, blank=True)
    end_time = models.DateTimeField(null=True, blank=True)
    notes = models.TextField(blank=True)

    def __str__(self):
        return f"{self.structure} - {self.get_change_type_display()} @ {self.recorded_at}"

    class Meta:
        ordering = ["-recorded_at"]
        verbose_name_plural = "structure histories"


class StructureFilterPreset(models.Model):
    """A saved set of structure filter IDs."""

    name = models.CharField(max_length=100, unique=True)
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, related_name="+"
    )
    solar_system_ids = models.JSONField(default=list, blank=True)
    corporation_ids = models.JSONField(default=list, blank=True)
    alliance_ids = models.JSONField(default=list, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        ordering = ["name"]


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
