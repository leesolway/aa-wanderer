"""
Template tags for wanderer, following the same pattern as hr_tags.zkillboard_url:
a small simple_tag that builds a zKillboard link, used as
{% zkillboard_url 'system' solar_system.id as zkill %}.
"""

from django import template

register = template.Library()

ZKILLBOARD_BASE = "https://zkillboard.com"

# zKillboard uses a different path segment per entity kind.
_ZKILLBOARD_PATHS = {
    "character": "character",
    "corporation": "corporation",
    "alliance": "alliance",
    "system": "system",
}


@register.simple_tag
def zkillboard_url(kind, entity_id):
    """Return the zKillboard URL for an entity, or '' if entity_id/kind is unusable."""
    path = _ZKILLBOARD_PATHS.get(kind)
    if not path or not entity_id:
        return ""
    return f"{ZKILLBOARD_BASE}/{path}/{entity_id}/"
