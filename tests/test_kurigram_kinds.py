from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest
from pyrogram import enums

from channels_cleaner.config import Settings
from channels_cleaner.telegram.kurigram_gateway import KurigramGateway


def dialog(chat_type: enums.ChatType, chat_id: int, *, creator: bool = False, admin: bool = False) -> Any:  # noqa: ANN401
    chat = SimpleNamespace(
        id=chat_id,
        type=chat_type,
        title=f"chat {chat_id}",
        username=None,
        is_creator=creator,
        is_admin=admin,
        members_count=None,
        photo=None,
    )
    return SimpleNamespace(
        chat=chat, top_message=None, unread_messages_count=0, folder_id=0, raw=SimpleNamespace(notify_settings=None)
    )


class FakeClient:
    def __init__(self, dialogs: list[Any]) -> None:
        self._dialogs = dialogs

    async def get_dialogs(self) -> AsyncIterator[Any]:
        for item in self._dialogs:
            yield item


@pytest.mark.asyncio
async def test_forums_count_as_supergroups_and_the_rest_is_left_out(tmp_path: Path) -> None:
    gateway = KurigramGateway(Settings(data_dir=tmp_path, _env_file=None))  # pyright: ignore[reportCallIssue]
    gateway._client = FakeClient(  # type: ignore[assignment]  # noqa: SLF001
        [
            dialog(enums.ChatType.CHANNEL, 1),
            dialog(enums.ChatType.SUPERGROUP, 2),
            dialog(enums.ChatType.FORUM, 3, creator=True),
            dialog(enums.ChatType.FORUM, 4, admin=True),
            dialog(enums.ChatType.GROUP, 5),  # a basic group: not covered
            dialog(enums.ChatType.PRIVATE, 6),
            dialog(enums.ChatType.BOT, 7),
            dialog(enums.ChatType.DIRECT, 8),  # a channel's direct messages
        ]
    )
    gateway._started = True  # noqa: SLF001
    found = {info.id: (info.kind, info.role) async for info in gateway.iter_channels()}
    assert found == {
        1: ("channel", "member"),
        2: ("supergroup", "member"),
        3: ("supergroup", "owner"),
        4: ("supergroup", "admin"),
    }
