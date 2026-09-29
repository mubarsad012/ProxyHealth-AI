"""``POST /v1/feedback`` (API_CONTRACT §3.12; D-31): increments a content-free counter.

Only the enum/identifier tuple of ``feedback/store.py`` is persisted; the id is a fresh ULID.
``resource_id`` must be a vetted-DB id and ``model_id`` a configured model (or a model-style slug);
anything else is counted as ``other`` so no client text reaches ``var/feedback_counts.sqlite``.
"""

from functools import partial
from typing import Annotated

from fastapi import APIRouter, Depends
from starlette.concurrency import run_in_threadpool

from proxyhealth_api.contracts.feedback import FeedbackRequest, FeedbackResponse
from proxyhealth_api.deps import get_feedback_store, get_resources, get_settings
from proxyhealth_api.errors import error_responses
from proxyhealth_api.feedback.store import FeedbackStore
from proxyhealth_api.resources.loader import ResourceRepo
from proxyhealth_api.settings import Settings

router = APIRouter(prefix="/v1", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse, responses=error_responses(400))
async def feedback(
    req: FeedbackRequest,
    store: Annotated[FeedbackStore, Depends(get_feedback_store)],
    resources: Annotated[ResourceRepo, Depends(get_resources)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> FeedbackResponse:
    record = partial(
        store.record,
        known_resource=lambda rid: resources.get(rid) is not None,
        known_models=(settings.model_pro, settings.model_fast),
    )
    feedback_id = await run_in_threadpool(record, req)
    return FeedbackResponse(received=True, id=feedback_id)
