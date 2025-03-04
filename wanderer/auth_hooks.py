"""
Auth hooks with support for dynamic hooks (as opposed to the usual statically defined hooks in the code).

This part still requires a lot of testing

Code ~~stolen~~inspired by
https://github.com/Solar-Helix-Independent-Transport/allianceauth-discord-multiverse/blob/5dff96ddc783ae1a6752e500cab9bd432e653a97/aadiscordmultiverse/auth_hooks.py

"""

from django.db.models.signals import post_delete, post_save
from django.template.loader import render_to_string
from django.utils.translation import gettext_lazy as _

from allianceauth import hooks
from allianceauth.notifications.models import Notification
from allianceauth.services.hooks import ServicesHook, get_extension_logger

from .models import WandererManagedMap
from .urls import urlpatterns

logger = get_extension_logger(__name__)


class WandererManagedMapService(ServicesHook):
    """Service for managing a wanderer map ACL with the auth"""

    def __init_subclass__(cls, managed_map: WandererManagedMap):
        super().__init_subclass__()
        cls.managed_map = managed_map

    def __init__(self):
        ServicesHook.__init__(self)
        self.urlpatterns = urlpatterns
        self.access_perm = "wanderer.basic_access"

        self.name = f"wmm:{self.managed_map.wanderer_url}/{self.managed_map.map_slug}"

        self.service_ctrl_template = "wanderer/wmm_services_ctrl.html"

    def render_services_ctrl(self, request):
        return render_to_string(
            self.service_ctrl_template,
            {
                "title": self.managed_map.name,
                "url": str(self.managed_map),
                "has_account": self.managed_map.user_has_account(request.user),
                "map_id": self.managed_map.id,
            },
        )

    def show_service_ctrl(self, user):
        return self.managed_map.accessible_by(user)

    def delete_user(self, user, notify_user=False) -> bool:
        map_name = self.managed_map.name
        logger.info("Deleting user %s from map %s", user, map_name)
        try:
            self.managed_map.delete_user(user)
            if notify_user:
                Notification.objects.notify_user(
                    user,
                    _(f"Account removed from {map_name}"),
                    _(
                        f"Your characters have been removed from the wanderer map {map_name}"
                    ),
                    Notification.Level.WARNING,
                )
            return True
        except Exception as e:
            logger.error("Couldn't delete the user properly: %s", e)
            return False

    def validate_user(self, user):
        logger.debug("Validating user %s account on %s", user, self)
        if self.managed_map.user_has_account(
            user
        ) and not self.managed_map.accessible_by(user):
            logger.info("Removing user %s account on %s", user, self)
            self.delete_user(user, notify_user=True)


def add_del_callback(*args, **kwargs):
    """
    This works great at startup of auth, however has a bug where changes
    made during operation are only captured on a single thread.
    TLDR restart auth after adding a new server
    """
    # Get a list of all map info to check in our hook list
    map_add = list(WandererManagedMap.objects.all())
    # Spit out the ID's for troubleshooting
    logger.info(f"Processing Maps {map_add}")

    # Loop all services and look for our specific hook classes
    for h in hooks._hooks.get("services_hook", []):
        if isinstance(h(), WandererManagedMapService):
            # This is our hook
            # h is an instanced WandererManagedMapService hook with a wanderermap
            if h.managed_map in map_add:
                # this is a known map so remove it from our list of knowns
                map_add.remove(h.managed_map)
            else:
                # This one was deleted remove the hook.
                del h

    # Loop to setup what is missing ( or everything on first boot )
    for map in map_add:
        # What guild_id
        logger.info(f"Adding map {map}")
        # This is the magic to instance the hook class with a new Class Name
        # this way there are no conflicts at runtime
        guild_class = type(
            f"WandererManagedMapService'{map}'",  # New class name
            (WandererManagedMapService,),
            {},  # Super class
            managed_map=map,
        )
        # This adds the hook to the services_hook group to be loaded when needed.
        hooks.register("services_hook", guild_class)


post_save.connect(add_del_callback, sender=WandererManagedMap)
post_delete.connect(add_del_callback, sender=WandererManagedMap)
