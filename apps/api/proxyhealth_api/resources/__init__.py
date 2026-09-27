"""Vetted resource DB (WP3). WP0 ships empty ``ResourceRepo``/``RulesRepo`` stubs."""

from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.resources.rules_repo import FixedNotice, RulesRepo

__all__ = ["FixedNotice", "ResourceRepo", "RulesRepo"]
