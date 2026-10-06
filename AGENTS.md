# AGENTS.md

This file provides guidance to coding agents when working with code in this
repository.

## Overview

Ouranos-core is a Python 3.11+ async server that manages Gaia instances. It
receives Gaia's data through a message broker, stores it with async
SQLAlchemy, and serves it to the frontend over a FastAPI REST API and
Socket.IO. Extra functionalities are added through plugins.

## Essential Commands

Always go through `uv`, bare `python` / `pytest` might not find the packages.

```bash
# Install everything (extras: mariadb/postgresql; groups: test/qc)
uv sync --all-groups
```

Run these **in order** after any change, fixing each before the next:

```bash
uv run ruff check .                                                     # 1. lint
uv run ty check src/ouranos                                             # 2. type check
uv run pytest tests/ -v                                                 # 3. tests
uv run pytest tests/web_server/test_routes.py -k TestHardware -v        # (scoped test if needed)
uv run coverage run -m pytest && uv run coverage report --show-missing  # 4. coverage
```

After changing `gaia-validators`, `event-dispatcher` or `sqlalchemy-wrapper`
locally, reinstall it into the venv (`uv pip install -e <path>`) before type
checking or testing.

## High-Level Architecture

```
core/
├── config/                            config + contract versions (consts.py)
├── database/models/                   ORM models (app / gaia / system / archives / logging)
│   ├── abc.py                         Base, CRUDMixin, CacheMixin, ArchivableMixin
│   └── caching.py                     caching decorators, CachedCRUDMixin
└── email/                             mail sending + Jinja templates

main.py / cli.py                       entry point, starts the functionalities below
├── Aggregator                         aggregator/main.py        - Gaia-facing side
│   ├── GaiaEvents                     aggregator/events.py      - handles Gaia's events (counterpart of gaia's `Events`)
│   ├── SkyWatcher                     aggregator/sky_watcher.py - weather + sun times
│   ├── Archiver                       aggregator/archiver.py    - moves old rows to archive tables
│   └── FileServer                     aggregator/file_server.py - camera uploads (Starlette)
├── WebServer                          web_server/               - frontend-facing side
│   ├── routes/                          REST API (FastAPI)
│   ├── events/                          ClientEvents, Socket.IO namespace
│   └── auth.py, user_session.py         guards, session cookie
└── Plugins                            sdk/plugin.py, sdk/functionality.py - optionally in subprocesses

Events flow: Gaia → [dispatcher] → GaiaEvents → [internal dispatcher] → WebServer → frontend
```

- `tests/conftest.py`: `config` (session) and `db` (class-scoped) fixtures
- `tests/class_fixtures.py`: `*Aware` mixins seeding the DB for a test class
- `tests/data/`: test payloads and users

Shared data types come from the companion package **`gaia_validators`**
(imported as `gv`); look there for `gv.*` definitions.

## Key Development Patterns

### Database

- Use one `db.scoped_session()` per unit of work and pass the session down.
  **Never nest `scoped_session()`**: the inner block commits and closes the
  outer session.
- Never `commit()` inside model methods or helpers, the caller owns the
  transaction.
- Import every new model module before `db.init()` runs, or its queries fail
  with `UnboundExecutionError`.
- Recent-data models carrying an archive table use `ArchivableMixin`; archive
  models don't.

### Caching

- Caches are currently per-process: invalidation doesn't reach the other 
  processes, only the TTL bounds staleness there.
- Write through the model's `create` / `update` / `delete`, never with a raw
  statement, or the cache keeps the old row. This matters for `User`, whose
  `sessions_valid_from` drives session revocation.
- Load any relationship you'll read later before a cached instance is
  expunged.

### Aggregator events

- Stack handler decorators in this order: `@registration_required` →
  `@validate_payload(Model)` → `@dispatch_to_application`.
- Use `gv.empty` as the missing-argument sentinel and test it with
  `is not gv.empty`.
- Access dispatcher properties only after startup; they raise `RuntimeError`
  before.
- Trust connected Gaia instances: the broker's credentials are the trust
  boundary, so don't check a payload's `engine_uid` against the sender.

### Web server

- Truncate to the second (`utc_now_second()`) anything compared with a
  session token's `iat`.
- Set / delete the session cookie only through `set_session_cookie()` /
  `delete_session_cookie()`.

### Error handling

- Prefer degraded operation over crashing: a failing functionality or plugin
  is logged and skipped.
- Use `assert` for internal contracts; raise only at public API boundaries.

### Type checking

- To suppress a `ty` error, add `# ty: ignore[rule]` inline, never a bare
  `# type: ignore`.
- Define TypedDicts at module level, not inside functions.

### Style

- Async-first, type hints everywhere, `TYPE_CHECKING` imports to break
  cycles.

## Testing

- Mark async test classes with `@pytest.mark.asyncio`.
- Seed data by inheriting the `*Aware` mixins from `tests/class_fixtures.py`
  (e.g. admin routes need `UsersAware`), not by inserting rows by hand.
- Route tests live in `tests/web_server/routes/<resource>.py` and only run
  once imported into `tests/web_server/test_routes.py`.
- Name route tests `Test<Resource><Scope>` / `test_<action>[_<qualifier>][_<outcome>]`,
  with failure suffixes `_failure_anon`, `_failure_not_<role>`,
  `_failure_payload`, `_failure_wrong_<thing>`, `_failure_not_found`
  (see `routes/hardware.py`).
- Use the `client` / `client_user` / `client_operator` / `client_admin`
  fixtures for authenticated requests.
- The config is immutable: patch the helper reading it
  (`monkeypatch.setattr`), never `monkeypatch.setitem` on the config.
- Read a re-issued session cookie from `response.cookies`, not
  `client.cookies`.
- `test_web_server.py::TestWebServer::test_lifecycle` binds port 5000; if it
  alone fails, check nothing else is listening there.

## Changelog & Versioning

- Keep `CHANGELOG.md`'s `## Unreleased` up to date (Keep-a-Changelog,
  sections `Added` / `Changed` / `Removed` / `Fixed` / `Security` /
  `Development`). Group entries by theme and end each with its PR numbers,
  e.g. `(#478)`. Tooling, tests and CI go under `Development`.
- Mark breaking API changes with **Breaking** and bump the matching contract.
- Check the changelog before any version bump.
- The app version is independent of Gaia and the frontend. Compatibility is
  carried by the contracts in `core/config/consts.py`: bump `GAIA_CONTRACT`
  only for a breaking change to dispatcher events or payloads (together with
  Gaia), `REST_CONTRACT` / `SOCKETIO_CONTRACT` for breaking changes to the
  frontend-facing API.

## Critical Notes

- **Do NOT** edit existing revisions in `migrations/versions/`. A schema change
  needs a new one, named `<rev>_<PR>_<slug>.py`, and human review.
- **Do NOT** modify `.github/workflows/`.
- **Do NOT** run `scripts/install.sh`, `update_ouranos.sh`, `start.sh` or
  `stop.sh` against the real machine. Use `scripts/utils/sandbox.sh`.
  `tests/test_scripts.py` guards their version strings.
- Edit launcher scripts in this repo's `scripts/` only; the install directory's
  `scripts/` is a deployed copy overwritten on update.
- **Do NOT** launch the app through `uv run` in `start.sh`, nor match its
  process by name: `$!` must be the app's PID, and the process is renamed
  late.
