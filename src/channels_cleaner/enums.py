"""Closed sets of values shared by the gateway, the database and the API.

Values are the lowercase member names (``auto()`` on a StrEnum): the same strings sit in the database, travel through
the API and are compared in the UI.
"""

from enum import StrEnum, auto


class ChatKind(StrEnum):
    CHANNEL = auto()
    # Forums too: a separate type in Kurigram, a supergroup for Telegram
    SUPERGROUP = auto()


class ChatRole(StrEnum):
    """What the user is in a chat."""

    MEMBER = auto()
    ADMIN = auto()
    OWNER = auto()


class MediaKind(StrEnum):
    PHOTO = auto()
    VIDEO = auto()
    ANIMATION = auto()
    DOCUMENT = auto()
    AUDIO = auto()
    VOICE = auto()
    POLL = auto()
    STICKER = auto()
    OTHER = auto()


class Decision(StrEnum):
    KEEP = auto()
    UNSUBSCRIBE = auto()
    MUTE = auto()
    ARCHIVE = auto()
    # "Later": back of the deck, forgotten on the next launch
    SKIP = auto()


class DecisionStatus(StrEnum):
    PENDING = auto()
    APPLIED = auto()
    FAILED = auto()


class JobStatus(StrEnum):
    RUNNING = auto()
    FINISHED = auto()
    CANCELLED = auto()
    ERROR = auto()
    # Still running when the app stopped
    INTERRUPTED = auto()


class SortMode(StrEnum):
    # Never posted first, then the longest silence
    DEAD = auto()
    UNREAD = auto()


class ArchiveFilter(StrEnum):
    """Which part of the chat list the deck shows."""

    ALL = auto()
    ACTIVE = auto()
    ARCHIVED = auto()


class RoleFilter(StrEnum):
    """The two decks: chats the user is just in, and the ones they run (admin or owner)."""

    MEMBER = auto()
    MANAGED = auto()


#: final decisions that need a call to Telegram
ACTION_DECISIONS = (Decision.UNSUBSCRIBE, Decision.MUTE, Decision.ARCHIVE)
#: applied actions the app can take back (a left chat is gone for good)
REVERSIBLE_ACTIONS = (Decision.MUTE, Decision.ARCHIVE)
