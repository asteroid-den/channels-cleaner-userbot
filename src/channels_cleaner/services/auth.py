"""Login state machine: QR (with optional 2FA), phone + code, logout."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Literal

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


class AuthError(Exception):
    """A user-facing auth failure (wrong code, wrong password, …)."""

    def __init__(self, code: str, message: str, retry_after: int | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.retry_after = retry_after


class AuthService:
    def __init__(self, gateway: TelegramGateway, database: DatabaseManager, bus: EventBus) -> None:
        self._gw = gateway
        self._database = database
        self._bus = bus
        self.state = AuthState()
        self._lock = asyncio.Lock()
        self._qr_task: asyncio.Task[None] | None = None
        self._on_login: list[Callable[[TgUser], Awaitable[None]]] = []

    def on_login(self, callback: Callable[[TgUser], Awaitable[None]]) -> None:
        self._on_login.append(callback)

    @property
    def account_id(self) -> int:
        if self.state.status != "authorized" or self.state.user is None:
            msg = "Not authorized"
            raise NotAuthorizedError(msg)

        return self.state.user.id

    def _publish(self) -> None:
        self._bus.publish(TOPIC, "state", **self.state.snapshot())

    def _set(self, status: AuthStatus, **changes: Any) -> None:  # noqa: ANN401 - AuthState fields
        self.state = AuthState(status=status, user=self.state.user, **changes)
        self._publish()

    # --- lifecycle ---------------------------------------------------------------------
    async def start(self) -> None:
        try:
            user = await self._gw.start()

        except NotAuthorizedError:
            user = await self._gw.start()  # stored session was revoked; retry fresh

        if user is not None:
            await self._logged_in(user)

        else:
            self._set("unauthorized")

    def connect_failed(self, exc: BaseException) -> None:
        """No connection to Telegram on start: the UI says so while the app keeps trying."""
        self._set("unauthorized", error=f"connect_failed: {exc or type(exc).__name__}")

    async def stop(self) -> None:
        await self._cancel_qr()

    async def _logged_in(self, user: TgUser) -> None:
        profile = self._gw.device_profile

        async with self._database.session() as session:
            dao = DAO(session)
            await dao.upsert_account(user, profile.to_json() if profile else None, base.utc_now())
            await dao.commit()

        self.state = AuthState(status="authorized", user=user)
        self._publish()

        for callback in self._on_login:
            try:
                await callback(user)

            except Exception:
                log.exception("on_login callback failed")

    # --- QR ------------------------------------------------------------------------------
    async def start_qr(self) -> None:
        async with self._lock:
            self._require_unauthorized()
            await self._cancel_qr()
            self._set("qr")
            self._qr_task = asyncio.create_task(self._qr_loop(), name="qr-login")

    async def _cancel_qr(self) -> None:
        task, self._qr_task = self._qr_task, None

        if task is not None and not task.done():
            task.cancel()

            with contextlib.suppress(asyncio.CancelledError):
                await task

    async def _qr_loop(self) -> None:
        try:
            while True:
                try:
                    token = await self._gw.qr_export()

                except FloodWaitError as exc:
                    self._set("qr", error=f"flood_wait:{exc.seconds}")
                    await asyncio.sleep(exc.seconds)
                    continue

                self._set("qr", qr_url=token.url, qr_expires_at=token.expires_at)

                try:
                    user = await self._gw.qr_wait()

                except QrExpiredError:
                    continue

                self._qr_task = None  # we're about to finish; don't let anyone cancel us
                await self._logged_in(user)
                return

        except PasswordNeededError:
            self._qr_task = None
            await self._to_password()

        except asyncio.CancelledError:
            raise

        except Exception as exc:
            log.exception("QR login failed")
            self._set("unauthorized", error=str(exc) or type(exc).__name__)

    # --- phone + code --------------------------------------------------------------------
    async def send_code(self, phone: str) -> None:
        async with self._lock:
            self._require_unauthorized()
            await self._cancel_qr()

            try:
                await self._gw.send_code(phone)

            except FloodWaitError as exc:
                raise AuthError(code="flood_wait", message=str(exc), retry_after=exc.seconds) from exc

            except GatewayError as exc:
                raise AuthError(code="invalid_phone", message=str(exc)) from exc

            self._set("code", phone=phone)

    async def sign_in(self, code: str) -> None:
        async with self._lock:
            if self.state.status != "code":
                raise AuthError(code="bad_state", message="No code was requested")

            try:
                user = await self._gw.sign_in_code(code)

            except PasswordNeededError:
                await self._to_password()
                return

            except FloodWaitError as exc:
                raise AuthError(code="flood_wait", message=str(exc), retry_after=exc.seconds) from exc

            except GatewayError as exc:
                raise AuthError(code="invalid_code", message=str(exc)) from exc

            await self._logged_in(user)

    # --- 2FA -----------------------------------------------------------------------------
    async def _to_password(self) -> None:
        hint = None

        with contextlib.suppress(Exception):
            hint = await self._gw.password_hint()

        self._set("password", password_hint=hint)

    async def check_password(self, password: str) -> None:
        async with self._lock:
            if self.state.status != "password":
                raise AuthError(code="bad_state", message="Password is not expected now")

            try:
                user = await self._gw.check_password(password)

            except FloodWaitError as exc:
                raise AuthError(code="flood_wait", message=str(exc), retry_after=exc.seconds) from exc

            except GatewayError as exc:
                self._set("password", password_hint=self.state.password_hint)
                raise AuthError(code="invalid_password", message=str(exc)) from exc

            await self._logged_in(user)

    # --- logout --------------------------------------------------------------------------
    async def log_out(self, *, wipe_data: bool) -> None:
        async with self._lock:
            await self._cancel_qr()
            user = self.state.user
            await self._gw.log_out()

            if wipe_data and user is not None:
                async with self._database.session() as session:
                    dao = DAO(session)
                    await dao.wipe_account(user.id)
                    await dao.commit()

            self.state = AuthState(status="starting")
            user_after = await self._gw.start()

            if user_after is not None:  # should not happen, but keep state honest
                await self._logged_in(user_after)

            else:
                self._set("unauthorized")

    async def cancel(self) -> None:
        """Abort an in-progress login and go back to the method picker."""
        async with self._lock:
            if self.state.status == "authorized":
                return

            await self._cancel_qr()
            self._set("unauthorized")

    def _require_unauthorized(self) -> None:
        if self.state.status == "authorized":
            raise AuthError(code="bad_state", message="Already authorized")
