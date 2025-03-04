from django.core.management import BaseCommand

from allianceauth.services.hooks import get_extension_logger

from wanderer.tasks import cleanup_all_access_lists

logger = get_extension_logger(__name__)


class Command(BaseCommand):
    """Cleanup utility"""

    help = "Runs the cleanup command on all registered access lists"

    def handle(self, *args, **options):
        logger.info("Management command to cleanup access lists")
        cleanup_all_access_lists.delay()
        logger.info("Command success started")
