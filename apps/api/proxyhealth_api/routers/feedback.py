"""``POST /v1/feedback`` (API_CONTRACT §3.12; D-31). WP0 stub acknowledges without storing."""

from typing import Annotated

from fastapi import APIRouter, Depends

from proxyhealth_api.contracts.feedback import FeedbackRequest, FeedbackResponse
from proxyhealth_api.deps import get_feedback_store
from proxyhealth_api.errors import error_responses
from proxyhealth_api.feedback.store import FeedbackStore

router = APIRouter(prefix="/v1", tags=["feedback"])


@router.post("/feedback", response_model=FeedbackResponse, responses=error_responses(400))
async def feedback(
    req: FeedbackRequest, store: Annotated[FeedbackStore, Depends(get_feedback_store)]
) -> FeedbackResponse:
    return FeedbackResponse(received=True, id=store.record(req))
