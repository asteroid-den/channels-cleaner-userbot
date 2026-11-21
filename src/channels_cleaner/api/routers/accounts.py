from fastapi import APIRouter

from channels_cleaner.api import errors, models
from channels_cleaner.api.dependencies import ContextDep, DAODep

router = APIRouter(prefix="/accounts", tags=["accounts"])


@router.get("", responses=errors.error_responses())
async def get_accounts(ctx: ContextDep, dao: DAODep) -> models.AccountsResponse:
    active = ctx.auth.state.user.id if ctx.auth.state.status == "authorized" and ctx.auth.state.user else None
    return models.AccountsResponse(
        items=[
            models.Account(
                id=account.id,
                first_name=account.first_name,
                last_name=account.last_name,
                username=account.username,
                active=account.id == active,
                chats=await dao.count_channels(account.id),
                pending=await dao.count_pending(account.id),
            )
            for account in await dao.list_accounts()
        ]
    )


@router.post(
    "/{account_id}/activate",
    responses=errors.error_responses(errors.AccountNotFound, errors.ApplyJobRunning, errors.TelegramError),
)
async def post_activate_account(account_id: int, ctx: ContextDep) -> models.AuthStateResponse:
    await ctx.switch_account(account_id)
    return models.AuthStateResponse.model_validate(ctx.auth.state)


@router.post("/add", responses=errors.error_responses(errors.ApplyJobRunning, errors.TelegramError))
async def post_add_account(ctx: ContextDep) -> models.AuthStateResponse:
    """Connects a new session: the login screen then logs in another account, the others stay."""
    await ctx.add_account()
    return models.AuthStateResponse.model_validate(ctx.auth.state)
