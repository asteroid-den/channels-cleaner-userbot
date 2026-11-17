from __future__ import annotations

from pathlib import Path

from channels_cleaner.telegram.device_profiles import all_profiles, load_or_create


def test_profiles_are_complete_and_unique() -> None:
    profiles = all_profiles()
    assert len(profiles) >= 30
    assert len({p.name for p in profiles}) == len(profiles)

    for profile in profiles:
        kwargs = profile.client_kwargs()
        assert all(kwargs.values()), profile
        assert profile.lang_pack == "tdesktop"
        assert profile.system_lang_code.split("-")[0] == profile.lang_code


def test_profile_is_sticky(tmp_path: Path) -> None:
    path = tmp_path / "account.device.json"
    first = load_or_create(path)
    assert path.exists()
    assert all(load_or_create(path) == first for _ in range(5))


def test_corrupted_profile_is_rerolled(tmp_path: Path) -> None:
    path = tmp_path / "account.device.json"
    path.write_text("{oops", "utf-8")
    assert load_or_create(path) in all_profiles()
