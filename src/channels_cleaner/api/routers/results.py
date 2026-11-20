"""The deck's saved prefs and what the results screen shows: stats and the export of the chats left."""

import json
from typing import Annotated, Literal

from fastapi import APIRouter, Query, Response
from fastapi.responses import JSONResponse

from channels_cleaner.api import errors, models, utils
from channels_cleaner.api.dependencies import AccountIdDep, DAODep
from channels_cleaner.enums import ChatKind, RoleFilter
from channels_cleaner.services import deck, stats

router = APIRouter(tags=["results"])


@router.get("/prefs", responses=errors.error_responses(errors.NotAuthorized))
async def get_prefs(dao: DAODep, account_id: AccountIdDep) -> models.DeckPrefsResponse:
    prefs = await deck.prefs(dao, account_id)
    return models.DeckPrefsResponse(**prefs.model_dump())


@router.put("/prefs", responses=errors.error_responses(errors.NotAuthorized))
async def put_prefs(body: models.DeckPrefsRequest, dao: DAODep, account_id: AccountIdDep) -> models.DeckPrefsResponse:
    await dao.set_setting(account_id, deck.PREFS_KEY, body.model_dump(mode="json"))
    await dao.commit()
    return models.DeckPrefsResponse(**body.model_dump())


@router.get("/stats", responses=errors.error_responses(errors.NotAuthorized))
async def get_stats(
    dao: DAODep, account_id: AccountIdDep, kind: ChatKind = ChatKind.CHANNEL, role: RoleFilter = RoleFilter.MEMBER
) -> models.StatsResponse:
    return models.StatsResponse.model_validate(await stats.collect(dao, account_id, kind, role))


@router.get(
    "/export", response_class=Response, responses={**errors.error_responses(errors.NotAuthorized), **utils.EXPORT}
)
async def get_export(
    dao: DAODep,
    account_id: AccountIdDep,
    format_: Annotated[Literal["csv", "json"], Query(alias="format")] = "csv",
    kind: ChatKind = ChatKind.CHANNEL,
    role: RoleFilter = RoleFilter.MEMBER,
) -> Response:
    rows = await stats.export_rows(dao, account_id, kind, role)
    filename = f"unsubscribed-{kind}s.{format_}"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}

    if format_ == "json":
        return JSONResponse(json.loads(json.dumps(rows, default=str)), headers=headers)

    return Response(stats.to_csv(rows), media_type="text/csv; charset=utf-8", headers=headers)
