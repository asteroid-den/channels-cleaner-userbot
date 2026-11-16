# Channels Cleaner

Swipe through every Telegram channel you're subscribed to — Tinder-style — and leave the ones
you no longer read. Runs entirely on your own computer: a small Python server (Kurigram userbot +
FastAPI) and a Vue web UI opened in your browser.

- **Log in with a QR code** (or phone + code), with two-step verification supported.
- **One card per channel**: avatar, description, subscribers, unread count, last post preview,
  muted/archived badges, and an "activity" label.
- **Swipe or use the keyboard**: ← unsubscribe, → keep, ↓ later, `M` mute, `A` archive,
  `Ctrl+Z` undo, `Enter` review.
- **Two orders**: dead channels first, or most unread first, each reversible.
- **Nothing happens until you confirm.** Decisions queue up; the review screen applies them one
  by one with polite pauses and handles Telegram flood waits.
- **Results and export**: stats, plus a CSV/JSON list of everything you left (with `t.me`
  links in case you want something back).
- English and Russian, dark and light themes.

## Requirements

- Python 3.12+ and [uv](https://docs.astral.sh/uv/)
- Node.js 22.18+ (only to build the UI)

## Run it

```bash
npm --prefix frontend ci && npm --prefix frontend run build
uv run channels-cleaner
```

A browser tab opens at <http://127.0.0.1:8765>. Scan the QR code from Telegram on your phone:
**Settings → Devices → Link Desktop Device**.

Want to look around without a Telegram account? Use mock mode with generated channels:

```bash
uv run channels-cleaner --mock
```

(Mock QR codes are "scanned" automatically; the phone code is `12345`, and with
`CC_MOCK_2FA=1` the password is `mock`.)

### Options

| CLI flag        | Env var                     | Default                  |
| --------------- | --------------------------- | ------------------------ |
| `--host`        | `CC_HOST`                   | `127.0.0.1`              |
| `--port`        | `CC_PORT`                   | `8765`                   |
| `--mock`        | `CC_MOCK=1`                 | off                      |
| `--no-browser`  | `CC_NO_BROWSER=1`           | opens a tab              |
|                 | `CC_DATA_DIR`               | `./data`                 |
|                 | `CC_API_ID` / `CC_API_HASH` | Telegram Desktop's pair  |

Settings can also go in a `.env` file (see [`.env.example`](.env.example)).

## Where your data lives

Everything is in `./data` (git-ignored):

- `sessions/account.session` is your Telegram session. Treat it like a password.
- `sessions/account.device.json` is the device profile this session presents to Telegram (see
  below).
- `cleaner.sqlite3` holds the channel cache, your decisions and stats.
- `media/` caches avatars and post thumbnails.

**Log out and delete local data** in the account menu terminates the session on Telegram's side
and wipes all of the above for that account.

## Notes on the Telegram client

- By default the app uses the public Telegram Desktop `api_id`/`api_hash`. You can use your own
  from <https://my.telegram.org/apps> via `CC_API_ID`/`CC_API_HASH`. Using a third-party client
  is at your own risk under Telegram's Terms of Service.
- On first login a random, plausible Telegram Desktop device profile (OS, app version,
  language) is picked from [`device_profiles.json`](src/channels_cleaner/telegram/device_profiles.json)
  and **kept for the life of the session**. It does not change on every start.
- Channels you own or administer are never shown.
- Actions run sequentially with a 1.5–3 s pause between them. If Telegram responds with a flood
  wait, the job sleeps (the UI shows a countdown) and continues. Stop it at any time: unapplied
  decisions stay queued.

## Development

```bash
uv sync                       # backend deps
npm --prefix frontend ci      # frontend deps

uv run channels-cleaner --mock --dev --no-browser   # API on :8765
npm --prefix frontend run dev                        # UI on :5173, proxies /api
```

Checks (the same ones CI runs):

```bash
uv run ruff check && uv run ruff format --check && uv run mypy && uv run pytest
cd frontend && npm run lint && npm run format:check && npm run test && npm run build
```

### Layout

```
src/channels_cleaner/
  telegram/   gateway protocol, Kurigram + mock implementations, device profiles
  services/   auth state machine, sync, lazy channel info/media, apply job, stats
  api/        FastAPI routes (REST + Server-Sent Events)
  db.py       SQLite schema + repository
frontend/src/
  stores/     Pinia stores (auth, deck, apply, ui)
  views/      Login, Deck, Review, Apply, Results
  components/ swipe deck, card, filmstrip, …
```

## License

[MIT](LICENSE)
