"""FastAPI dependencies reading the objects the lifespan stored on ``app.state`` (BUILD_PLAN §4.1).

Tests build the app with ``create_app(Settings(...))`` and never touch module globals.
"""

from typing import TYPE_CHECKING

from fastapi import Request

from proxyhealth_api.settings import Settings

if TYPE_CHECKING:
    from proxyhealth_api.ai.failover import AIService
    from proxyhealth_api.ai.keypool import KeyPool
    from proxyhealth_api.ai.provider import AIProvider
    from proxyhealth_api.demo.fixtures import FixtureStore
    from proxyhealth_api.feedback.store import FeedbackStore
    from proxyhealth_api.packs.base import BasePack, LanguageTable
    from proxyhealth_api.packs.cache import PackCache
    from proxyhealth_api.resources.loader import ResourceRepo
    from proxyhealth_api.resources.rules_repo import RulesRepo


def get_settings(request: Request) -> Settings:
    settings: Settings = request.app.state.settings
    return settings


def get_provider(request: Request) -> "AIProvider":
    provider: AIProvider = request.app.state.provider
    return provider


def get_keypool(request: Request) -> "KeyPool | None":
    keypool: KeyPool | None = request.app.state.keypool
    return keypool


def get_ai(request: Request) -> "AIService":
    ai: AIService = request.app.state.ai
    return ai


def get_resources(request: Request) -> "ResourceRepo":
    repo: ResourceRepo = request.app.state.resources
    return repo


def get_rules(request: Request) -> "RulesRepo":
    rules: RulesRepo = request.app.state.rules
    return rules


def get_packs(request: Request) -> "BasePack":
    packs: BasePack = request.app.state.packs
    return packs


def get_pack_cache(request: Request) -> "PackCache":
    cache: PackCache = request.app.state.pack_cache
    return cache


def get_languages(request: Request) -> "LanguageTable":
    languages: LanguageTable = request.app.state.languages
    return languages


def get_fixtures(request: Request) -> "FixtureStore":
    fixtures: FixtureStore = request.app.state.fixtures
    return fixtures


def get_feedback_store(request: Request) -> "FeedbackStore":
    store: FeedbackStore = request.app.state.feedback_store
    return store


def get_request_id(request: Request) -> str:
    rid: str = request.state.request_id
    return rid
