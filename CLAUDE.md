# Channels Cleaner — notes for Claude

Local tool: Kurigram userbot + FastAPI + Vue UI. The user logs in to Telegram (QR or phone, 2FA),
the app pulls every broadcast channel they're subscribed to, shows them as Tinder-like cards
(swipe/keys: keep, unsubscribe, later, mute, archive), and applies the queued actions after a
review screen. Runs on the user's own machine only (127.0.0.1, no auth, not a server/VPS app).

Talk to the user in **Russian**. Code, comments, commits and README are in English.

## Repo state (as of 2026-11-17)

- **Released and public** (2026-11-17). Repo `asteroid-den/telegram-channels-cleaner` is public;
  `telegram-channels-cleaner` 1.0.0 and 1.0.1 are on PyPI, image `ghcr.io/asteroid-den/telegram-channels-cleaner`
  (1.0.1, amd64+arm64, public). 1.0.1 = same app, fixed Docker build (UI stage on
  `$BUILDPLATFORM`; 1.0.0's image never got pushed). Tag `v0.9.0` = the old generic UI (local only).
- Work goes through branches + PRs into `main` (merge commits). Push only when the user says so
  for that push; **never push tags** — the user tags releases (`release.yml` checks the tag
  against `__version__`, publishes to PyPI via trusted publishing, then GHCR).
- History was rewritten once to drop co-author trailers (PR #1 closed by the force-push).
- Plan agreed with the user: README (English, screenshots from mock mode, honest note about the
  TDesktop api_id + device profiles, session = full account access) → make the repo public →
  phone access (pairing QR + cookie, mobile layout with mockups first).
- Commit author email = personal gmail from global git config (already public); keep it.
- `mockups/` — static HTML mockups. Ignored via `.git/info/exclude`, not committed.
- `data/` — local sessions/DB/media (gitignored). Contains the user's mock DB from earlier runs.

Code style: ruff ALL (120 cols), pyright, blank lines around blocks (see the user memory on tooling).
Commit style: small logical commits, conventional prefixes (`feat(api):`, `fix(ui):`, `design(tool):`…),
**no `Co-Authored-By` trailer** (the user removed them from history on 2026-11-17). Branches for iterations after v1.

## Commands

```bash
uv sync && npm --prefix frontend ci           # deps (Node 22.18+, nvm default is 22)
npm --prefix frontend run build               # builds into src/channels_cleaner/static (gitignored)
uv run telegram-channels-cleaner --mock                # fake Telegram; real account: drop --mock
uv run telegram-channels-cleaner --mock --dev          # API only; plus `npm --prefix frontend run dev` (:5173)
```
Checks (= CI): `uv run ruff check && uv run ruff format --check && uv run pyright && uv run pytest`;
`cd frontend && npm run lint && npm run format:check && npm run test && npm run build`.
**Before every commit with Python changes**: `python3 -I .local/unstick_blocks.py src/channels_cleaner tests`
then `uv run ruff format` — blank lines around if/for/while/try/with/match and before elif/else/except/finally
(user's style). `--check` only reports. `.local/` is local-only (in `.git/info/exclude`), not in the repo or CI.
Mock mode: QR auto-"scans" after ~4 s; phone code `12345`; `CC_MOCK_2FA=1` → password `mock`.
Settings via `CC_*` env / `.env` (see `.env.example`): API id/hash (default = public TDesktop 2040),
data dir, host/port, mock knobs, apply delay range.

## Architecture

```
src/channels_cleaner/
  cli.py          port pre-check (friendly msg if our app already runs), opens browser only after
                  uvicorn started; browser.py opens it quietly (xdg-open/open/os.startfile)
  app.py          FastAPI factory, error→HTTP mapping, SPA fallback for static/
  context.py      AppContext wires everything; boot task runs auth.start(); clears "skip" on start
  config.py       Settings (pydantic-settings, CC_ prefix)
  db.py           aiosqlite, hand-written migrations (MIGRATIONS list; #2 added channels.pulse)
  events.py       in-process pub/sub → SSE (api/sse.py: snapshot event first, then live, pings)
  pulse.py        weekly post counts (26 weeks) from ≤100 post dates; unseen weeks = None
  telegram/
    gateway.py    Protocol; kurigram_gateway.py (real) and mock_gateway.py (generated channels)
    device_profiles.json  36 TDesktop-like profiles (user's 24 + 12 added); picked once per
                  session and persisted as data/sessions/account.device.json — never re-rolled
  services/       auth (state machine), sync, channels (lazy full info + pulse + media cache),
                  apply (sequential job, 1.5–3 s jitter, FloodWait sleep+retry, cancel), stats
  api/routes.py   all /api endpoints (auth, channels, decisions, apply, prefs, stats, export)
frontend/src/     Vue 3 + Vite + TS, Pinia, vue-router, vue-i18n (en/ru), Tailwind v4
  stores/         auth (SSE), deck (queue, undo history, prefetch 8 ahead), apply (SSE), ui
  components/     SwipeDeck (pointer swipe + fly-out), ChannelCard, PulseChart, AppHeader…
  views/          Login, Deck (3 columns), Review, Apply (avatar deck animation), Results
  utils/color.ts  dominant avatar colour → --ch/--ch2 CSS vars (useChannelColor composable)
```

Key behaviours / decisions (agreed with the user):
- Broadcast channels and supergroups (`channels.kind`, migration 4); anything the user owns/admins is
  excluded; plain basic groups are not covered. Archive included (flagged). One sync pass covers both
  kinds (a per-kind sync would mark the other kind `gone`); the deck, trail, stats and export take
  `?kind=`, review/apply are shared across kinds (`counts.pending_other` drives the dot on the
  header switcher). Lists synced before supergroups existed are re-synced once (`synced_kinds` setting).
  Wording that differs for groups lives under `group.*` in i18n (`useKindI18n().tk`).
- Archive filter (all / active / archived) lives in the deck prefs (`prefs.archive`, per account) and narrows
  the deck, trail and its counters for either kind; endpoints that return counts without `?archive=` read it
  from the saved prefs. Header: kind | archive | sort.
- Idea for later (user is thinking about it): extra tabs for chats the user owns/admins (2x2 with kind);
  leaving an owned/admin chat is destructive, so `unsubscribe` would need to be off by default there.
- Decisions: keep/skip are final immediately; unsubscribe/mute/archive are `pending` until the
  apply job. "Skip" = back of the deck, forgotten on next launch. Undo = DELETE decision.
- Full info (GetFullChannel) and pulse (raw `messages.GetHistory`, limit 100, no parsing) are
  fetched lazily per card with a semaphore of 1; cached 72 h. Rows without pulse are refetched.
- Sort: "dead first" (never-posted, then oldest last post) or "most unread", each reversible;
  prefs stored per account in DB. Language/theme in localStorage, dark theme default.
- Kurigram: `connect()` manually (start() would prompt interactively), QR via built-in
  `pyrogram.qrlogin.QRLogin` (handles DC migration); after login → disconnect + `start()`.

## Design (branch design/tool, mockup "B")

Flat panels + hairlines, data first. Fonts bundled via @fontsource: Jost (headings + verdict figure),
Onest (text), JetBrains Mono (numbers/keys). v1 token names kept (`surface`, `border`, `muted`,
`accent`, `danger`…) with new values, plus `ch`/`ch2` = current channel colour from its avatar.
Deck (deck-v2, chosen from mockups/deck-v2.html): no side columns. Header = sort + progress bar
(decided/total, segmented by decision, '+1' chip flies in) + summary pill (popover: counters, ETA,
history+undo, next, Review). Fanned stack; card layout C (one verdict figure). Left/right of the
card are click zones (unsubscribe/keep) with cursor glow + card lean. Keycaps under the stage.
Progress bar = chronological trail of decisions (counts.trail, one letter each). Rewind: hover the
bar → TrailLoupe (15 fanned avatars), click to jump; Ctrl+←/→ step through decided cards; deck =
trail[cursor:] + undecided; edits are in place (decided_at kept); "Back to undecided" button.
Changing an applied mute/archive sets decisions.reverts → apply job unmutes/unarchives first.

The user rejected the retro "press" look; wants modern digital but not generic SaaS.
**For any visual change: render 2–3 mockups and let the user pick before implementing.**

## Verification tips / gotchas

- The desktop app's Browser pane is usually hidden → rAF/CSS transitions stall and screenshots
  are stale. Use headless system Chrome via Playwright instead:
  `uv run --no-project --with playwright python script.py` with
  `p.chromium.launch(executable_path="/usr/bin/google-chrome", headless=True)`.
  Cached Playwright Firefox doesn't match the current Playwright version.
- Start test servers with `CC_DATA_DIR=<scratch dir> CC_NO_BROWSER=1 ... --mock --port 87xx`
  so the user's `data/` isn't touched. Stop with `kill $(lsof -t -i :PORT -sTCP:LISTEN)` —
  `pkill -f "telegram-channels-cleaner ..."` matches its own shell and kills the command (exit 144).
- User's browser is Firefox (snap); its GTK/sandbox warnings in the terminal are harmless.

## Open items

- Card drag fix (fe87e4c) verified in Chrome only — user to confirm in Firefox.
- Nothing tested on a real Telegram account yet (only connect + QR export smoke test).
  Watch flood waits from the extra GetHistory call per card; lower prefetch depth if needed.
- Optional: bundle only latin+cyrillic font subsets; 5 moderate `npm audit` issues are dev-only.
- Decide what to do with `design/press` (delete?) and when to merge `design/tool` into `main`.
- Spec extras agreed for later: multi-account support (DB already keyed by account_id).
