"""What the routes take from FastAPI: the app's context, the logged-in account, a database session."""

from __future__ import annotations

from collections.abc import AsyncIterator
from typing import Annotated

from fastapi import Depends, Request

from channels_cleaner.context import AppContext
from channels_cleaner.database import DAO


def get_context(request: Request) -> AppContext:
    context: AppContext = request.app.state.ctx
    return context


ContextDep = Annotated[AppContext, Depends(get_context)]


def get_account_id(ctx: ContextDep) -> int:
    return ctx.auth.account_id  # raises NotAuthorizedError -> 401


AccountIdDep = Annotated[int, Depends(get_account_id)]


async def get_dao(ctx: ContextDep) -> AsyncIterator[DAO]:
    """A session per request; a route that writes commits it."""
    async with ctx.database.session() as session:
        yield DAO(session)


DAODep = Annotated[DAO, Depends(get_dao)]
