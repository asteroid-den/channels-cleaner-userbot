from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from channels_cleaner.api import errors, models, utils
from channels_cleaner.api.dependencies import AccountIdDep, ContextDep
from channels_cleaner.api.sse import sse_response
from channels_cleaner.services.apply import TOPIC

router = APIRouter(prefix="/apply", tags=["apply"])


@router.post("", responses=errors.error_responses(errors.NotAuthorized, errors.ApplyJobRunning))
async def post_apply(ctx: ContextDep, account_id: AccountIdDep) -> models.ApplyStateResponse:
    return models.ApplyStateResponse.model_validate(await ctx.apply.start(account_id))


@router.post("/cancel", responses=errors.error_responses())
async def post_cancel_apply(ctx: ContextDep) -> models.ApplyStateResponse:
    ctx.apply.cancel()
    return models.ApplyStateResponse.model_validate(ctx.apply.state)


@router.get("/state", responses=errors.error_responses())
async def get_apply_state(ctx: ContextDep) -> models.ApplyStateResponse:
    return models.ApplyStateResponse.model_validate(ctx.apply.state)


@router.get("/events", response_class=StreamingResponse, responses={**errors.error_responses(), **utils.EVENT_STREAM})
async def get_apply_events(request: Request, ctx: ContextDep) -> StreamingResponse:
    return sse_response(request, ctx.bus, TOPIC, ctx.apply.state.snapshot)
