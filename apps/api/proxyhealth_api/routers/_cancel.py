"""Stop a model-calling request's work when its client goes away (``AI_PROVIDER=openai_compat``;
LOCAL_AI.md §5).

uvicorn does not cancel the app's task on a disconnect, and the middlewares are plain ASGI, so an
abandoned ``/v1/analyze`` (the reading screen's Cancel, a closed tab, a lost network) would keep
the one loopback model slot busy for up to ``OPENAI_COMPAT_TIMEOUT_S`` while the reader's
immediate retry waits behind it, its queue wait counted against its own budget.

``run_until_disconnect`` runs the work as a task and watches the ASGI receive channel (the body
has already been read) for ``http.disconnect``. When it arrives the task is cancelled:
``CancelledError`` passes through ``AIService`` (it catches ``Exception`` only), the provider's
``finally`` releases its semaphore, and httpx closes the socket, so Ollama stops generating.
Thread-pool work already started (page decoding) finishes on its own. Nothing is sent to anyone:
the ``499`` response goes to a closed connection and only reaches the content-free access log.
Gemini and the mock keep a plain ``await`` (their calls are short and pay per token).
"""

import asyncio
import contextlib
from collections.abc import Coroutine
from typing import Any

from starlette.requests import Request
from starlette.responses import Response

from proxyhealth_api.logging_ import log_event
from proxyhealth_api.settings import Settings

CLIENT_GONE_STATUS = 499  # "client closed request" (nginx); never reaches a client


async def _client_gone(request: Request) -> None:
    """Returns once the client has disconnected (the request body was consumed already)."""
    while True:
        message = await request.receive()
        if message["type"] == "http.disconnect":
            return


async def run_until_disconnect[T](
    request: Request, work: Coroutine[Any, Any, T], settings: Settings, *, request_id: str
) -> T | Response:
    """``await work``; on ``openai_compat``, cancel it as soon as the client disconnects."""
    if settings.ai_provider != "openai_compat":
        return await work
    task = asyncio.ensure_future(work)
    watcher = asyncio.ensure_future(_client_gone(request))
    try:
        done, _ = await asyncio.wait({task, watcher}, return_when=asyncio.FIRST_COMPLETED)
        if task in done:
            return task.result()
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        log_event(request_id=request_id, route="request.client_gone", status=CLIENT_GONE_STATUS)
        return Response(status_code=CLIENT_GONE_STATUS)
    finally:
        for pending in (task, watcher):
            if not pending.done():
                pending.cancel()
