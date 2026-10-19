"""
Signals that trigger Astropath ACL re-syncs.

Three events invalidate an ACL:
  - A user's main character changes (post_save on UserProfile)
  - A user account is deleted (pre_delete on User - group data still accessible)
  - A user is added to or removed from a group (m2m_changed on User.groups.through)
"""

from django.contrib.auth.models import Group, User
from django.db.models.signals import m2m_changed, post_save, pre_delete
from django.dispatch import receiver

from allianceauth.authentication.models import UserProfile
from allianceauth.services.hooks import get_extension_logger

logger = get_extension_logger(__name__)


def _acl_ids_for_groups(group_ids: list) -> list[int]:
    """Returns distinct ACL IDs that have a mapping for any of the given groups."""
    from wanderer.models import AstropathACLMapping

    return list(
        AstropathACLMapping.objects.filter(group_id__in=group_ids)
        .values_list("acl_id", flat=True)
        .distinct()
    )


def _queue_syncs_for_user(user: User) -> None:
    """Queues sync tasks for all Astropath ACLs mapped to the user's groups."""
    from wanderer.tasks import sync_astropath_acl

    group_ids = list(user.groups.values_list("id", flat=True))
    if not group_ids:
        return
    acl_ids = _acl_ids_for_groups(group_ids)
    for acl_id in acl_ids:
        logger.debug("Queuing Astropath sync for ACL %d (user %s)", acl_id, user)
        sync_astropath_acl.delay(acl_id)


@receiver(post_save, sender=UserProfile)
def on_profile_save(sender, instance: UserProfile, update_fields, **kwargs):
    """Re-sync when a user's main character changes."""
    # If update_fields is specified and doesn't touch main_character, skip.
    if update_fields is not None and not (
        "main_character" in update_fields or "main_character_id" in update_fields
    ):
        return
    _queue_syncs_for_user(instance.user)


@receiver(pre_delete, sender=User)
def on_user_pre_delete(sender, instance: User, **kwargs):
    """Re-sync when a user account is deleted (group data still accessible here)."""
    _queue_syncs_for_user(instance)


@receiver(m2m_changed, sender=User.groups.through)
def on_group_membership_changed(sender, action, instance, pk_set, model, **kwargs):
    """Re-sync when a user is added to or removed from a group."""
    if action not in ("post_add", "post_remove"):
        return
    if not pk_set:
        return

    # m2m_changed fires in two directions depending on which side initiated the change:
    #   user.groups.add(group)     → instance=User,  model=Group, pk_set={group_id, ...}
    #   group.user_set.add(user)   → instance=Group, model=User,  pk_set={user_id, ...}
    if model is Group:
        group_ids = list(pk_set)
    else:
        # instance is the Group; pk_set are user IDs we don't need here
        group_ids = [instance.pk]

    from wanderer.tasks import sync_astropath_acl

    acl_ids = _acl_ids_for_groups(group_ids)
    for acl_id in acl_ids:
        logger.debug("Queuing Astropath sync for ACL %d (group membership changed)", acl_id)
        sync_astropath_acl.delay(acl_id)
