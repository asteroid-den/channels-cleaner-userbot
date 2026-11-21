"""Login state machine: QR (with optional 2FA), phone + code, logout."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

from channels_cleaner.api.errors import FloodWait, InvalidCode, InvalidPassword, InvalidPhone, LoginStepUnexpected
from channels_cleaner.database import DAO, DatabaseManager
from channels_cleaner.database.models import base
from channels_cleaner.events import EventBus
from channels_cleaner.telegram.gateway import TelegramGateway
from channels_cleaner.telegram.types import (
    FloodWaitError,
    GatewayError,
    NotAuthorizedError,
    PasswordNeededError,
    QrExpiredError,
    TgUser,
)

log = logging.getLogger(__name__)

TOPIC = "auth"

AuthStatus = Literal["starting", "unauthorized", "qr", "code", "password", "authorized"]


@dataclass(slots=True)
class AuthState:
    status: AuthStatus = "starting"
    user: TgUser | None = None
    qr_url: str | None = None
    qr_expires_at: datetime | None = None
    password_hint: str | None = None
    phone: str | None = None
    error: str | None = None

    def snapshot(self) -> dict[str, Any]:
        data = asdict(self)
        data["qr_expires_at"] = self.qr_expires_at.isoformat() if self.qr_expires_at else None
        return data


class AuthService:
    def __init__(self, gateway: TelegramGateway, database: DatabaseManager, bus: EventBus) -> None:
        self.gateway = gateway
        self.database = database
        self.bus = bus
        self.state = AuthState()
        self.lock = asyncio.Lock()
        self.qr_task: asyncio.Task[None] | None = None
        self.login_callbacks: list[Callable[[TgUser], Awaitable[None]]] = []

    def on_login(self, callback: Callable[[TgUser], Awaitable[None]]) -> None:
        self.login_callbacks.append(callback)

    @property
    def account_id(self) -> int:
        if self.state.status != "authorized" or self.state.user is None:
            msg = "Not authorized"
            raise NotAuthorizedError(msg)

        return self.state.user.id

    def publish(self) -> None:
        self.bus.publish(TOPIC, "state", **self.state.snapshot())

    def set_status(self, status: AuthStatus, **changes: Any) -> None:  # noqa: ANN401 - AuthState fields
        self.state = AuthState(status=status, user=self.state.user, **changes)
        self.publish()

    # --- lifecycle ---------------------------------------------------------------------
    async def start(self) -> None:
        try:
            user = await self.gateway.start()

        except NotAuthorizedError:
            user = await self.gateway.start()  # stored session was revoked; retry fresh

        if user is not None:
            await self.logged_in(user)

        else:
            self.set_status("unauthorized")

    def connect_failed(self, exc: BaseException) -> None:
        """No connection to Telegram on start: the UI says so while the app keeps trying."""
        self.set_status("unauthorized", error=f"connect_failed: {exc or type(exc).__name__}")

    async def stop(self) -> None:
        await self.cancel_qr()

    async def logged_in(self, user: TgUser) -> None:
        profile = self.gateway.device_profile

        async with self.database.session() as session:
            dao = DAO(session)
            await dao.upsert_account(user, profile.to_json() if profile else None, base.utc_now())
            await dao.commit()

        self.state = AuthState(status="authorized", user=user)
        self.publish()

        for callback in self.login_callbacks:
            try:
                await callback(user)

            except Exception:
                log.exception("on_login callback failed")

    # --- QR ------------------------------------------------------------------------------
    async def start_qr(self) -> None:
        async with self.lock:
            self.require_unauthorized()
            await self.cancel_qr()
            self.set_status("qr")
            self.qr_task = asyncio.create_task(self.qr_loop(), name="qr-login")

    async def cancel_qr(self) -> None:
        task, self.qr_task = self.qr_task, None

        if task is not None and not task.done():
            task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def qr_loop(self) -> None:
        try:
            while True:
                try:
                    token = await self.gateway.qr_export()

                except FloodWaitError as exc:
                    self.set_status("qr", error=f"flood_wait:{exc.seconds}")
                    await asyncio.sleep(exc.seconds)
                    continue

                self.set_status("qr", qr_url=token.url, qr_expires_at=token.expires_at)

                try:
                    user = await self.gateway.qr_wait()

                except QrExpiredError:
                    continue

                self.qr_task = None  # we're about to finish; don't let anyone cancel us
                await self.logged_in(user)
                return

        except PasswordNeededError:
            self.qr_task = None
            await self.to_password()

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            log.exception("QR login failed")
            self.set_status("unauthorized", error=str(exc) or type(exc).__name__)

    # --- phone + code --------------------------------------------------------------------
    async def send_code(self, phone: str) -> None:
        async with self.lock:
            self.require_unauthorized()
            await self.cancel_qr()

            try:
                await self.gateway.send_code(phone)

            except FloodWaitError as exc:
                raise FloodWait(retry_after=exc.seconds) from exc

            except GatewayError as exc:
                raise InvalidPhone(reason=str(exc)) from exc

            self.set_status("code", phone=phone)

    async def sign_in(self, code: str) -> None:
        async with self.lock:
            if self.state.status != "code":
                raise LoginStepUnexpected(reason="No code was requested")

            try:
                user = await self.gateway.sign_in_code(code)

            except PasswordNeededError:
                await self.to_password()
                return

            except FloodWaitError as exc:
                raise FloodWait(retry_after=exc.seconds) from exc

            except GatewayError as exc:
                raise InvalidCode(reason=str(exc)) from exc

            await self.logged_in(user)

    # --- 2FA -----------------------------------------------------------------------------
    async def to_password(self) -> None:
        hint = None

        with contextlib.suppress(Exception):
            hint = await self.gateway.password_hint()

        self.set_status("password", password_hint=hint)

    async def check_password(self, password: str) -> None:
        async with self.lock:
            if self.state.status != "password":
                raise LoginStepUnexpected(reason="Password is not expected now")

            try:
                user = await self.gateway.check_password(password)

            except FloodWaitError as exc:
                raise FloodWait(retry_after=exc.seconds) from exc

            except GatewayError as exc:
                self.set_status("password", password_hint=self.state.password_hint)
                raise InvalidPassword(reason=str(exc)) from exc

            await self.logged_in(user)

    # --- logout --------------------------------------------------------------------------
    async def log_out(self, *, wipe_data: bool) -> None:
        async with self.lock:
            await self.cancel_qr()
            user = self.state.user
            await self.gateway.log_out()

            if wipe_data and user is not None:
                async with self.database.session() as session:
                    dao = DAO(session)
                    await dao.wipe_account(user.id)
                    await dao.commit()

            self.state = AuthState(status="starting")
            user_after = await self.gateway.start()

            if user_after is not None:  # should not happen, but keep state honest
                await self.logged_in(user_after)

            else:
                self.set_status("unauthorized")

    async def cancel(self) -> None:
        """Abort an in-progress login and go back to the method picker."""
        async with self.lock:
            if self.state.status == "authorized":
                return

            await self.cancel_qr()
            self.set_status("unauthorized")

    def require_unauthorized(self) -> None:
        if self.state.status == "authorized":
            raise LoginStepUnexpected(reason="Already authorized")
