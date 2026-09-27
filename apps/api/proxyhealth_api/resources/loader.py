"""``ResourceRepo`` (BUILD_PLAN §4.1). WP0 stub: empty collections, version ``"0"``."""

from pathlib import Path

from proxyhealth_api.contracts.resources import Resource


class ResourceRepo:
    def __init__(self, resources: list[Resource], version: str) -> None:
        self._by_id = {r.id: r for r in resources}
        self._version = version

    @classmethod
    def load(cls, dir: Path) -> "ResourceRepo":  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        return cls([], "0")

    def all(self) -> list[Resource]:
        return list(self._by_id.values())

    def get(self, id: str) -> Resource | None:  # noqa: A002 - name fixed by BUILD_PLAN §4.1
        return self._by_id.get(id)

    def names(self) -> set[str]:
        return {r.name for r in self._by_id.values()}

    @property
    def version(self) -> str:
        return self._version
