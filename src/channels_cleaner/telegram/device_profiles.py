"""Telegram Desktop-like device metadata mixed into ``InitConnection``.

A profile is picked at random once per session and then persisted next to the session file:
changing the "device" on every launch would look far more suspicious than any single choice.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass
from functools import cache
from importlib import resources
from pathlib import Path
from typing import Any, TypedDict


class ClientKwargs(TypedDict):
    """The ``Client`` arguments a profile sets."""

    device_model: str
    system_version: str
    app_version: str
    lang_pack: str
    lang_code: str
    system_lang_code: str


@dataclass(slots=True, frozen=True)
class DeviceProfile:
    name: str
    device_model: str
    system_version: str
    app_version: str
    lang_pack: str
    lang_code: str
    system_lang_code: str

    def client_kwargs(self) -> ClientKwargs:
        return ClientKwargs(
            device_model=self.device_model,
            system_version=self.system_version,
            app_version=self.app_version,
            lang_pack=self.lang_pack,
            lang_code=self.lang_code,
            system_lang_code=self.system_lang_code,
        )

    def to_json(self) -> str:
        return json.dumps(asdict(self), ensure_ascii=False)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DeviceProfile:
        return cls(**{field: str(data[field]) for field in cls.__slots__})


@cache
def all_profiles() -> tuple[DeviceProfile, ...]:
    raw = resources.files(__package__).joinpath("device_profiles.json").read_text("utf-8")
    return tuple(DeviceProfile.from_dict(item) for item in json.loads(raw))


def random_profile(rng: random.Random | None = None) -> DeviceProfile:
    return (rng or random.SystemRandom()).choice(all_profiles())


def load_or_create(path: Path) -> DeviceProfile:
    """Return the profile stored at ``path``; pick and store a new one if there is none."""
    if path.exists():
        try:
            return DeviceProfile.from_dict(json.loads(path.read_text("utf-8")))

        except (ValueError, KeyError, TypeError):
            pass  # corrupted file: fall through and re-roll

    profile = random_profile()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(profile.to_json(), "utf-8")
    return profile
