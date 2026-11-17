"""Fake Telegram backend with generated channels — lets the whole UI run without an account."""

from __future__ import annotations

import asyncio
import json
import random
from collections.abc import AsyncIterator
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from html import escape
from pathlib import Path

from channels_cleaner.config import Settings
from channels_cleaner.telegram.device_profiles import DeviceProfile, all_profiles
from channels_cleaner.telegram.types import (
    ChannelFull,
    ChannelInfo,
    FloodWaitError,
    GatewayError,
    InvalidCodeError,
    InvalidPasswordError,
    InvalidPhoneError,
    MediaKind,
    NotAuthorizedError,
    PasswordNeededError,
    QrToken,
    TgUser,
)

MOCK_CODE = "12345"
MOCK_PASSWORD = "mock"
MOCK_USER = TgUser(id=777000111, first_name="Mock", last_name="User", username="mock_user")

_ADJ = [
    "Daily",
    "Crypto",
    "Tech",
    "Rust",
    "Python",
    "Frontend",
    "Indie",
    "Retro",
    "Quiet",
    "Night",
    "Urban",
    "Data",
    "Design",
    "Linux",
    "Space",
    "Coffee",
    "Vinyl",
    "Pixel",
]
_NOUN = [
    "Digest",
    "News",
    "Notes",
    "Memes",
    "Insights",
    "Weekly",
    "Radar",
    "Lab",
    "Corner",
    "Chronicles",
    "Feed",
    "Club",
    "Journal",
    "Signals",
    "Drops",
    "Hub",
]
_RU = [
    "Заметки разработчика",
    "Новости за минуту",
    "Тихий канал",
    "Кофе и код",
    "Ночной эфир",
    "Типичный бэкендер",
    "Мемы про деплой",
    "Вечерний дайджест",
    "Книжная полка",
    "Кино без спойлеров",
    "Путешествия налегке",
    "Сад и огород",
    "Финансы просто",
]
_TEXTS = [
    "Big update today: we shipped the thing everyone has been asking for. Details inside 👇",
    "Короткий пост о том, почему не стоит деплоить в пятницу вечером.",
    "Weekly roundup: 7 links worth your attention this week.",
    "Розыгрыш! Подпишись на три канала партнёров и получи шанс выиграть ничего.",
    "Thread: how we cut our cloud bill in half without rewriting anything.",
    "Сегодня без лонгрида — просто красивая фотография заката.",
    "Reminder: the meetup starts in an hour, stream link in the pinned message.",
    "Мы переезжаем! Новый канал по ссылке, этот скоро будет удалён.",
]
_ABOUT = [
    "Everything about modern backend development. No ads, no spam.",
    "Авторский канал о технологиях, жизни и всём остальном. По рекламе — в личку.",
    "Curated links, once a day. Sometimes twice.",
    "Канал, который вы забыли, что читаете.",
    None,
]
_MEDIA: list[MediaKind | None] = [None, None, None, "photo", "photo", "video", "document", "poll"]
_COLORS = ["#e17076", "#7bc862", "#e5ca77", "#65aadd", "#a695e7", "#ee7aae", "#6ec9cb", "#faa774"]


def _generate(count: int, seed: int = 42) -> dict[int, tuple[ChannelInfo, ChannelFull]]:
    rng = random.Random(seed)
    now = datetime.now(UTC)
    channels: dict[int, tuple[ChannelInfo, ChannelFull]] = {}
    for i in range(count):
        channel_id = -1001000000000 - i
        title = rng.choice(_RU) if rng.random() < 0.3 else f"{rng.choice(_ADJ)} {rng.choice(_NOUN)}"
        if any(info.title == title for info, _ in channels.values()):
            title = f"{title} #{i}"
        # Skewed activity: lots of fresh channels, a long tail of dead ones, some never posted.
        roll = rng.random()
        if roll < 0.04:
            last_post_at = None
        elif roll < 0.5:
            last_post_at = now - timedelta(hours=rng.uniform(0.2, 24 * 7))
        else:
            last_post_at = now - timedelta(days=rng.expovariate(1 / 160) + 7)
        unread = 0 if rng.random() < 0.25 else int(rng.expovariate(1 / 120))
        media = rng.choice(_MEDIA) if last_post_at else None
        members = int(rng.lognormvariate(8, 1.6))
        info = ChannelInfo(
            id=channel_id,
            title=title,
            username=None if rng.random() < 0.15 else f"mock_{i:03d}",
            unread_count=unread,
            is_muted=rng.random() < 0.3,
            is_archived=rng.random() < 0.15,
            members_count=members if rng.random() < 0.5 else None,
            photo_file_id=None if rng.random() < 0.1 else f"mock-photo-{i}",
            photo_unique_id=None if rng.random() < 0.1 else f"u{i}",
            last_post_id=rng.randint(10, 9000) if last_post_at else None,
            last_post_at=last_post_at,
            last_post_text=rng.choice(_TEXTS) if last_post_at and rng.random() < 0.9 else None,
            last_post_media=media,
        )
        if info.photo_file_id is None:
            info = replace(info, photo_unique_id=None)
        full = ChannelFull(about=rng.choice(_ABOUT), members_count=members)
        channels[channel_id] = (info, full)
    return channels


def _initials(title: str) -> str:
    words = [w for w in title.replace("#", " ").split() if w[:1].isalnum()]
    return "".join(w[0] for w in words[:2]).upper() or "?"


def _avatar_svg(title: str, color: str) -> str:
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 160 160">'
        f'<rect width="160" height="160" fill="{color}"/>'
        '<text x="50%" y="54%" dominant-baseline="middle" text-anchor="middle" '
        'font-family="system-ui, sans-serif" font-size="64" font-weight="600" fill="#fff">'
        f"{escape(_initials(title))}</text></svg>"
    )


def _thumb_svg(seed: int) -> str:
    rng = random.Random(seed)
    a, b = rng.sample(_COLORS, 2)
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 320 200">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        f'<stop offset="0" stop-color="{a}"/>'
        f'<stop offset="1" stop-color="{b}"/></linearGradient></defs>'
        '<rect width="320" height="200" fill="url(#g)"/>'
        f'<circle cx="{rng.randint(60, 260)}" cy="{rng.randint(40, 160)}" '
        f'r="{rng.randint(20, 60)}" '
        'fill="#fff" fill-opacity=".25"/></svg>'
    )


class MockGateway:
    """In-memory stand-in for :class:`KurigramGateway`.

    QR login is auto-"scanned" a few seconds after the code is shown; phone login accepts
    ``12345``; with ``CC_MOCK_2FA=1`` the password is ``mock``. Actions occasionally raise
    flood waits and errors so the UI paths for them can be exercised.
    """

    qr_scan_after: float = 4.0

    def __init__(self, settings: Settings, *, seed: int = 42) -> None:
        self._settings = settings
        self._state_path = settings.data_dir / "mock_session.json"
        self._channels = _generate(settings.mock_channels, seed)
        self._authorized = False
        self._awaiting_password = False
        self._phone: str | None = None
        self._qr_round = 0
        self._rng = random.Random(seed + 1)
        self._profile = all_profiles()[0]
        self.action_delay = 0.15

    @property
    def device_profile(self) -> DeviceProfile | None:
        return self._profile

    async def start(self) -> TgUser | None:
        if self._state_path.exists():
            state = json.loads(self._state_path.read_text("utf-8"))
            self._authorized = bool(state.get("authorized"))
            gone = set(state.get("gone", []))
            self._channels = {k: v for k, v in self._channels.items() if k not in gone}
        return MOCK_USER if self._authorized else None

    async def stop(self) -> None:
        return None

    def _save(self, gone: set[int] | None = None) -> None:
        state = {"authorized": self._authorized, "gone": sorted(gone or set())}
        if self._state_path.exists() and gone is None:
            state["gone"] = json.loads(self._state_path.read_text("utf-8")).get("gone", [])
        self._state_path.parent.mkdir(parents=True, exist_ok=True)
        self._state_path.write_text(json.dumps(state), "utf-8")

    def _login(self) -> TgUser:
        if self._settings.mock_2fa:
            self._awaiting_password = True
            raise PasswordNeededError
        self._authorized = True
        self._save()
        return MOCK_USER

    def _require_auth(self) -> None:
        if not self._authorized:
            raise NotAuthorizedError("Not authorized")

    # --- auth ----------------------------------------------------------------------
    async def qr_export(self) -> QrToken:
        if self._authorized:
            raise GatewayError("Already authorized")
        self._qr_round += 1
        return QrToken(
            url=f"tg://login?token=mock-{self._qr_round}",
            expires_at=datetime.now(UTC) + timedelta(seconds=30),
        )

    async def qr_wait(self) -> TgUser:
        await asyncio.sleep(self.qr_scan_after)
        return self._login()

    async def send_code(self, phone: str) -> None:
        digits = "".join(ch for ch in phone if ch.isdigit())
        if len(digits) < 7:
            raise InvalidPhoneError("PHONE_NUMBER_INVALID")
        self._phone = phone

    async def sign_in_code(self, code: str) -> TgUser:
        if not self._phone:
            raise GatewayError("Request a code first")
        if code.strip() != MOCK_CODE:
            raise InvalidCodeError("PHONE_CODE_INVALID")
        return self._login()

    async def password_hint(self) -> str | None:
        return "it's literally 'mock'"

    async def check_password(self, password: str) -> TgUser:
        if not self._awaiting_password:
            raise GatewayError("Password is not expected now")
        if password != MOCK_PASSWORD:
            raise InvalidPasswordError("PASSWORD_HASH_INVALID")
        self._awaiting_password = False
        self._authorized = True
        self._save()
        return MOCK_USER

    async def log_out(self) -> None:
        self._authorized = False
        self._state_path.unlink(missing_ok=True)
        self._channels = _generate(self._settings.mock_channels)

    # --- channels --------------------------------------------------------------------
    async def iter_channels(self) -> AsyncIterator[ChannelInfo]:
        self._require_auth()
        for index, (info, _) in enumerate(list(self._channels.values())):
            if index % 25 == 0:
                await asyncio.sleep(0.05)  # pretend to paginate
            yield info

    async def get_full(self, channel_id: int) -> ChannelFull:
        self._require_auth()
        await asyncio.sleep(0.15)
        entry = self._channels.get(channel_id)
        if entry is None:
            raise GatewayError("CHANNEL_INVALID")
        return entry[1]

    async def recent_post_dates(self, channel_id: int, limit: int) -> list[datetime]:
        self._require_auth()
        entry = self._channels.get(channel_id)
        last = entry[0].last_post_at if entry is not None else None
        if last is None:
            return []
        rng = random.Random(channel_id)
        # A posting rate that matches how "alive" the channel looks; dead channels get a
        # slower rate so their pulse visibly fades out into the past.
        quiet_days = (datetime.now(UTC) - last).days
        rate = rng.choice([0.3, 0.8, 1.5, 3, 8]) if quiet_days < 14 else rng.choice([0.2, 0.5, 1])
        dates = [last]
        current = last
        while len(dates) < limit:
            current -= timedelta(days=rng.expovariate(rate) + 0.01)
            if (last - current).days > 400:
                break
            dates.append(current)
        return dates

    async def download_avatar(self, channel_id: int, file_id: str, dest: Path) -> Path | None:
        entry = self._channels.get(channel_id)
        if entry is None:
            return None
        path = dest.with_suffix(".svg")
        color = _COLORS[abs(channel_id) % len(_COLORS)]
        path.write_text(_avatar_svg(entry[0].title, color), "utf-8")
        return path

    async def download_post_thumb(
        self, channel_id: int, message_id: int, dest: Path
    ) -> Path | None:
        entry = self._channels.get(channel_id)
        if entry is None or entry[0].last_post_media not in {"photo", "video"}:
            return None
        path = dest.with_suffix(".svg")
        path.write_text(_thumb_svg(channel_id + message_id), "utf-8")
        return path

    # --- actions -----------------------------------------------------------------------
    async def _maybe_fail(self) -> None:
        await asyncio.sleep(self.action_delay)
        roll = self._rng.random()
        if roll < 0.05:
            raise FloodWaitError(self._rng.randint(3, 6))
        if roll < 0.08:
            raise GatewayError("CHANNEL_PRIVATE")

    async def leave(self, channel_id: int) -> None:
        self._require_auth()
        await self._maybe_fail()
        self._channels.pop(channel_id, None)
        gone: set[int] = set()
        if self._state_path.exists():
            gone = set(json.loads(self._state_path.read_text("utf-8")).get("gone", []))
        gone.add(channel_id)
        self._save(gone)

    async def mute(self, channel_id: int) -> None:
        self._require_auth()
        await self._maybe_fail()
        if channel_id in self._channels:
            info, full = self._channels[channel_id]
            self._channels[channel_id] = (replace(info, is_muted=True), full)

    async def archive(self, channel_id: int) -> None:
        self._require_auth()
        await self._maybe_fail()
        if channel_id in self._channels:
            info, full = self._channels[channel_id]
            self._channels[channel_id] = (replace(info, is_archived=True), full)

    async def unmute(self, channel_id: int) -> None:
        self._require_auth()
        await self._maybe_fail()
        if channel_id in self._channels:
            info, full = self._channels[channel_id]
            self._channels[channel_id] = (replace(info, is_muted=False), full)

    async def unarchive(self, channel_id: int) -> None:
        self._require_auth()
        await self._maybe_fail()
        if channel_id in self._channels:
            info, full = self._channels[channel_id]
            self._channels[channel_id] = (replace(info, is_archived=False), full)
