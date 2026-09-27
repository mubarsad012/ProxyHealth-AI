"""``FeedbackStore`` (BUILD_PLAN §4.1). WP0 stub: ``record`` returns ``"fb_stub"``, stores none."""

from pathlib import Path

from proxyhealth_api.contracts.feedback import FeedbackRequest


class FeedbackStore:
    def __init__(self, path: Path) -> None:
        self.path = path

    def record(self, req: FeedbackRequest) -> str:
        return "fb_stub"

    def counts(self) -> list[tuple[str, ...]]:
        return []
