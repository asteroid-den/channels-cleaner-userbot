from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from channels_cleaner.api import errors, models, utils
from channels_cleaner.api.dependencies import ContextDep
from channels_cleaner.api.sse import sse_response
from channels_cleaner.services.auth import TOPIC

router = APIRouter(prefix="/auth", tags=["auth"])

LOGIN_STEP = (errors.LoginStepUnexpected, errors.FloodWait, errors.TelegramError)


@router.get("/state", responses=errors.error_responses())
async def get_auth_state(ctx: ContextDep) -> models.AuthStateResponse:
    return models.AuthStateResponse.model_validate(ctx.auth.state)


@router.get("/events", response_class=StreamingResponse, responses={**errors.error_responses(), **utils.EVENT_STREAM})
async def get_auth_events(request: Request, ctx: ContextDep) -> StreamingResponse:
    return sse_response(request, ctx.bus, TOPIC, ctx.auth.state.snapshot)


@router.post("/qr/start", responses=errors.error_responses(errors.LoginStepUnexpected))
async def post_qr_login(ctx: ContextDep) -> models.AuthStateResponse:
    await ctx.auth.start_qr()
    return models.AuthStateResponse.model_validate(ctx.auth.state)


@router.post("/phone/send-code", responses=errors.error_responses(*LOGIN_STEP, errors.InvalidPhone))
async def post_send_code(body: models.SendCodeRequest, ctx: ContextDep) -> models.AuthStateResponse:
    await ctx.auth.send_code(body.phone.strip())
    return models.AuthStateResponse.model_validate(ctx.auth.state)


@router.post("/phone/sign-in", responses=errors.error_responses(*LOGIN_STEP, errors.InvalidCode))
async def post_sign_in(body: models.SignInRequest, ctx: ContextDep) -> models.AuthStateResponse:
    await ctx.auth.sign_in(body.code.strip())
    return models.AuthStateResponse.model_validate(ctx.auth.state)


@router.post("/password", responses=errors.error_responses(*LOGIN_STEP, errors.InvalidPassword))
async def post_password(body: models.CheckPasswordRequest, ctx: ContextDep) -> models.AuthStateResponse:
    await ctx.auth.check_password(body.password)
    return models.AuthStateResponse.model_validate(ctx.auth.state)


@router.post("/cancel", responses=errors.error_responses())
async def post_cancel_login(ctx: ContextDep) -> models.AuthStateResponse:
    await ctx.auth.cancel()
    return models.AuthStateResponse.model_validate(ctx.auth.state)


@router.post("/logout", responses=errors.error_responses(errors.ApplyJobRunning))
async def post_logout(body: models.LogoutRequest, ctx: ContextDep) -> models.AuthStateResponse:
    if ctx.apply.running:
        raise errors.ApplyJobRunning

    await ctx.sync.forget()
    ctx.channels.reset()
    await ctx.auth.log_out(wipe_data=body.wipe_data)
    return models.AuthStateResponse.model_validate(ctx.auth.state)
