# Changelog

## Unreleased

- `HardwareGroup` model introduced; measures and actuator groups linked to `Hardware`
  and `EnvironmentParameter`, reflecting Gaia's group-based actuator control
- "active" field added to the `Hardware` table
- "weather" event added
- `CRUDMixin.get_or_create()` added; race conditions in `update_or_create()` handled
  more robustly
- `Plugin.check_requirements()` override hook for startup validation
- `Plugin.create_run_command()` for defining custom CLI commands and groups
- `Plugin` setup and startup improved; `Functionality` runtime improved
- `Archiver` reworked and coupled more tightly with DB models to prevent drift
- DB revision checked at startup; `check_db_revision()` is launch-directory-agnostic
- DB migration handling eased; table creation managed through SQLAlchemy during updates
- `event-dispatcher` bumped to 0.6.x
- `uv` adopted for virtual environment and package management; GitHub workflows updated
- Unique constraints added to all `Association{...}` tables
- `GaiaEvents` and `CRUDMixin` cleaned up and improved

---

## 0.10.0 — 2025-10-14

- "plants" event added to communicate plant health data to Gaia
- "environmental_parameters" event removed (deprecated since 0.9.0)
- "management" route now returns actuator status based on whether at least one actuator
  is active
- Fix: hardware update CRUD request and payload validation issues
- Fix: hardware-plant relationship serialization
- `Hardware`, `Measure` and `Plant` guaranteed not to be linked more than once
- All `Mapped[datetime]` columns use `UtcDateTime`
- DB models using `_lookup_keys` now have a unique constraint
- `CRUDMixin`: `_on_conflict_do` support in `create` / `create_multiple` subclasses;
  `_get_lookup_keys` and related helpers moved from `Base` to `CRUDMixin`
- Log failures during `on_buffered_*` events
- Log to file enabled by default
- `start.sh` "foreground" option added for systemd integration
- `install.sh` and `update.sh` hardened: can be sourced without executing `main`;
  option to update only ouranos-core; per-package update scripts supported
- QC workflow added to CI/CD; tests reorganised into classes

---

## 0.9.0 — 2025-05-25

- Email service added: account confirmation, password reset, and mail-sending module
- Wiki improvements: article versions stored as compact diffs; tags on topics, articles
  and pictures; slugified URLs; picture tagging and file upload; `WikiArticlePicture`
  made a `CRUDMixin`
- "environmental_parameters" aggregator event split into three focused events; emitted
  at each weather update
- Health data treated as a special case of sensor data; routes and payload adapted for
  frontend consumption; "buffered_health_data" event added
- `GaiaEvents.validate_payload` converted to a decorator
- User "last_seen" tracking added; session cookie expiration extended; "remember me"
  no longer uses a session-limited token; `/auth/refresh_session` route added
- User deletion is now a soft delete; `User.get_by` supports AND / OR clauses
- Calendar events: time-window search, public events, visibility restricted for
  anonymous users, 31-day default window
- `CRUDMixin.create()` gains `_on_conflict_do` argument; `RecordMixin` made a subclass
  of `CRUDMixin`; `offset`, `limit` and `order_by` added to `CRUDMixin.get()`
- `SQLIntEnum` added to store `IntEnum` as integer in the database
- "memory" database replaced by a SQLite-backed "transient" database
- Engine / ecosystem connection timeout increased to 60 seconds
- FastAPI bumped to 0.115, pydantic to 2.11, uvicorn to 0.34
- Jinja2 removed from requirements
- Python 3.13 added to test matrix

---

## 0.8.0 — 2024-11-28

- Camera pictures received from Gaia stored via a Starlette-based file server;
  compressed image support in "picture_arrays" event; bulk upload route added;
  `StreamGaiaEvents` merged back into `GaiaEvents`
- Basic wiki added (static file delivery)
- Socket.IO join/leave room events added
- `aioCache`: SQLite-backed cache for sharing data across processes
- User caching added; fast paths for recent `Engine`s and `Ecosystem`s
- `CRUDMixin` made more robust: `lookup_keys` validation enforced, tolerant to primary
  keys other than "uid"; primary key consistency improved across tables
- System data format uniformized between API and WebSocket
- Brotli response compression added
- `anyio.Path` replaces `pathlib.Path` for non-blocking file I/O
- `asyncache` dependency removed
- GitHub Actions test suite with coverage added; in-memory SQLite used in tests
- Python 3.9 and 3.10 support dropped

---

## 0.7.1 — 2024-07-31

- Alembic added for database migrations
- Events updated to match Gaia's updated registration handshake
- `User.can()` method moved from `User` to `UserMixin`

---

## 0.7.0 — 2024-07-29

First release with a structured PR workflow.

- Gaia sensor alarms caught and logged
- "actuators_data" event replaces deprecated "actuator_data"; actuator records logged
  on each event; route added to query actuator history
- "ecosystems heartbeat" and "place_list" events added
- `registration_required` decorator re-registers unrecognised engines automatically;
  Gaia registration handshake improved; TTL added to "registration_ack" message
- Calendar events routes added
- Gaia warnings creation, update, and filtering routes added
- User management routes: get, update, soft delete / deactivate
- User information embedded in registration tokens; registration API returns same
  payload as login
- `lighting_method` field added to ecosystem creation and update routes
- `ConfigHelper` and `PathsHelper` introduced for robust config and path resolution
- Frontend address auto-added to allowed API origins
- SQLite-based logger added
- FastAPI lifespan events used properly; dispatcher v0.3.0;
  `BaseFunctionality` startup / shutdown made async
- Sensor skeleton response includes measure units
- System routes and DB models cleaned up
- Session key based on user agent only (remote address dropped)

---

## 0.6.0 — 2023-09-08

First release tracked in git (earlier versions were managed by hand).

The codebase was entirely rewritten from Flask / Flask-RESTX to **FastAPI**, with the
Vue frontend separated into its own project. Socket.IO is dropped as the communication
channel with Gaia in favour of the event dispatcher.

- "buffered_sensors_data" event added: logs sensor data buffered by Gaia during
  connection outages
- CORS: Vite and Node dev servers added as allowed origins in development mode
- `gaiaAggregator` and legacy `gaiaConfig` modules removed
- Absolute humidity and dew point measures supported
- Admin overview page; server info streamed to admin clients

---

## 0.5.2

Project renamed from gaiaWeb to **Ouranos**. This release also marks the beginning of
the frontend split: the Vue-based UI is extracted into a separate project, and
ouranos-core becomes a pure backend API server.

- Flask-RESTX adopted: API endpoints reorganised into namespaces under `src/app/routes/`
  (app, auth, gaia, weather, system); dedicated `src/api/` layer separates business
  logic from route definitions
- Event dispatcher integrated: inter-component communication is now event-driven;
  `configure_dispatcher()` called at startup in the new `main.py` entry point
- Database models reorganised into `src/database/models/` with dedicated files
  (`app.py`, `gaia.py`, `archives.py`, `system.py`) replacing a single models module
- Fine-grained permission model introduced: `Permission` flags (VIEW, EDIT, OPERATE,
  ADMIN) and `Role` model with per-route `@permission_required` decorator
- WebSocket event handlers moved to `src/app/events/` (`clients.py`, `gaia.py`)
- Redis caching refactored from `src/dataspace/` to `src/redis_cache.py`; TTL-based
  in-memory caches added for frequently accessed ecosystem data (`cachetools.TTLCache`)
- `src/consts.py` added for shared constants
- Config env var renamed from `GAIA_CONFIG` to `OURANOS_PROFILE`
- Flask-Migrate, Flask-Mail, Flask-WTF removed; Flask-CORS and marshmallow added

---

## 0.5.1

- License file added
- Minor configuration adjustments; no structural changes

---

## 0.5.0

First standalone gaiaWeb release. Gaia and Ouranos were previously a single combined
project (versions 0.0.1–0.4.0); 0.5.0 is the split, taking the `gaiaWeb` part as its
own project.

- Flask application factory (`create_app`) introduced; configuration profiles for
  development, testing, and production
- SQLAlchemy ORM replaces the `gaiaDatabase` SQL abstraction; multiple database binds:
  `db_app.db` (users and application data), `db_ecosystems.db`, `db_archive.db`
- Flask-Login for session-based user authentication
- Flask-SocketIO for real-time WebSocket communication with Gaia clients
- Flask-Migrate (Alembic) for database schema migrations
- Services architecture introduced: `archiver`, `weather`, `system_monitor`,
  `notifications`, `telegram_chat_bot`, `daily_recap`, `sun_times`, `webcam`,
  `calendar` — each service manages its own lifecycle and shares the scheduler
- Redis-based data caching layer (`src/dataspace/`)
- Flask-Mail for email notifications; Flask-WTF for form validation
- Blueprints: `auth`, `admin`, `main`, `api`, `errors`
- Wiki section added

---

*Versions 0.1.0–0.4.0 are from the combined Gaia + Ouranos era. Only the web server
(gaiaWeb) parts are described below.*

---

## 0.4.0 — March 2020

- Flask blueprints introduced: `auth`, `core`, `errors`
- User authentication added: registration, login, logout with password hashing
  (werkzeug)
- APScheduler background jobs: sensor data logged every 10 min, plant data every 15 min
- System resource monitoring added (CPU / RAM / disk via `psutil`), logged every 5 min
- Multi-ecosystem support in web routes: `/environment/<ecosystem>`,
  `/plants/<ecosystem>`
- Context processors inject user, ecosystems, plants, and warnings into every template
- Routes: `/home`, `/weather`, `/warning`, `/care/*`

---

## 0.3.0 — February 2020

- gaiaWeb established as a dedicated module, separated from gaiaEngine
- YAML cache files used as data source (replaces direct MySQL queries in routes)
- Routes expanded: `/sensors/overview`, `/sensors/<environment>`, `/sensors/settings`,
  `/weather`
- Multi-ecosystem support started; per-environment data visualisation with temporal
  history passed to templates

---

## 0.2.0 — December 2019

- Web server reorganised into the `Website/GaiaWeb/` directory; no significant
  web-specific changes

---

## 0.1.0 — September 2019

Initial version, a single combined Gaia + Ouranos project:

- Flask web app (`Hello.py`) with direct MySQL queries (MySQLdb)
- Routes: `/home`, `/environment`, `/plants`, `/care/*`, `/settings`, `/about`
- No authentication
