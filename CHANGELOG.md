# Changelog

---

## Unreleased

### Added
- Session revocation: a "sessions_valid_from" cutoff column on `User` (with its migration
  script) invalidating every session token issued before it, and `User.revoke_session_token()`
  to bump it (#415)
- "revoke_sessions" route, the "log out everywhere" counterpart to "logout"; it requires a
  fresh session (#415)
- "refresh_session" route re-issuing the session cookie with a new "iat", re-opening the
  freshness window that guards the sensitive routes; it requires the current user's
  credentials, as bumping "iat" is a re-authentication rather than a refresh (#415)
- `API_SECURE_COOKIES` config parameter (`OURANOS_API_SECURE_COOKIES`) setting the session
  cookie's "secure" flag (#414)
- `scripts/utils/pyproject_helpers.sh`, meant to be sourced by the plugins installation
  scripts: `add_dependency <name> [extras] [source]` declares a package in the master
  `pyproject.toml` (#429)
- nginx reverse-proxy template (`deploy/nginx/ouranos.conf`) exposing the frontend and the
  API behind a single port; the installation and update scripts expand it into
  `scripts/ouranos.conf` through `scripts/utils/gen_nginx.sh` (#425, #435)
- `mariadb` and `postgresql` optional dependencies, installing the matching async database
  driver (#427)
- `BaseLog`/`AccessLog` models ("system" bind, each indexed on timestamp + level) with
  `get_multiple()` to filter stored log entries by time window and level range, with
  pagination (#442)
- "logging" app service, which can only be enabled when `LOG_TO_DB` is set, with its
  operator-only "/logging/base" and "/logging/access" routes to read the stored logs,
  filtered by time window and level range (level names, case-insensitive), with
  pagination (#460)
- "connection_date" column on `Engine` and `Ecosystem` (with its migration script), set each
  time they connect (#441, #455)
- "in_config" column on `Service` (with its migration script) flagging the services that
  depend on the config file, currently only "email": enabling one whose config requirements
  are not met is refused with a 400 (#458)
- `GaiaWarning` and `FlashMessage` are archivable, into the new "warnings_archive" and
  "flash_message_archive" tables, after `WARNING_ARCHIVING_PERIOD` days (#483, #515)
- `Extension`, the base class of `Plugin` handling its routes, and
  `PluginManager.load_plugin()` to load a single plugin without registering them all
  (#421, #422)
- `Host` (`ouranos.sdk`), the root of an Ouranos process: it prepares the shared resources,
  starts its plugins (all or none), restarts their dead subprocess workers while running
  (with an exponential back-off for a worker that keeps dying), and stops them on a stop
  signal (#511, #512)

### Changed
- **Breaking**: the route formerly known as "refresh_session", which pushes back the session
  expiration date, is renamed "extend_session"; "refresh_session" now refreshes the token's
  "iat" instead (`REST_CONTRACT` bumped to 2) (#415)
- Users are now loaded from the whole session token rather than from its "user_id" field
  alone, on both the REST routes and the Socket.IO events; this is what makes the revocation
  cutoff enforceable (#415)
- Session ids are random rather than a hash of the browser's user agent, so a session is no
  longer rejected when the user agent changes (#414)
- Session freshness reduced from 15 hours to 15 minutes (#415)
- `LoginManager` removed, its behaviour folded into the new `web_server.user_session` module,
  which also hosts `SessionInfo` (#415)
- `set_session_cookie()` and `delete_session_cookie()` centralise the "secure" and "httponly"
  cookie flags (#415)
- The master `pyproject.toml` now declares every package installed alongside the core, and the
  installation and update scripts sync it exactly (`uv sync`, without `--all-packages
  --inexact`): commenting a dependency out is enough to disable a plugin, and recreating the
  virtual environment reinstalls exactly what is declared (#429)
- The master `pyproject.toml` is no longer regenerated on update, as it now belongs to the
  installation; an installation predating this change is migrated on its next update, keeping
  the plugins found in `lib/` and the database driver in use, while any other manually
  installed package has to be declared again (#429)
- The installation script installs Python 3.13 through `uv` rather than requiring a recent
  enough system interpreter (#429)
- The update script also updates the master `pyproject.toml`'s `requires-python` (#492)
- `opencv-python-headless` replaces `opencv-python` (#492)
- `uvloop` is now a required dependency, and processes run through `uvloop.run()` rather
  than `setup_loop()`, which is removed (#450)
- Log files: `ouranos.log` is rotated weekly and keeps 4 backups; "uvicorn.access" logs and
  the Socket.IO events (new "ouranos.web_server.socketio" logger) go to their own
  `access.log`, which replaces `uvicorn.log`, while the other Uvicorn logs go to
  `ouranos.log` (#412, #436, #437)
- Logged errors now carry their traceback (#438)
- DB logging (`LOG_TO_DB`) now goes through SQLAlchemy instead of a bespoke `log.sqlite`
  file: `SQLiteHandler` is replaced by `DBHandler`, bound to one of two tables depending on
  the logger it's attached to ("access"-flavoured loggers, "ouranos.web_server.socketio",
  "uvicorn.access", go to `AccessLog`, everything else to `BaseLog`), and keeps the full
  traceback of logged exceptions; writes are scheduled onto the app's own event loop rather
  than a dedicated logging thread (#413, #442)
- The `base_logs`/`access_logs` tables are now always created, whatever `LOG_TO_DB`, and
  no longer lazily by `DBHandler` (#460)
- Sensor alarms are now logged every minute by their own scheduled step, run right after the
  sensors data one, rather than every `SENSOR_LOGGING_PERIOD` alongside it: since
  `SensorAlarm.create_or_lengthen()` extends a single row instead of inserting a new one, the
  finer period costs nothing and keeps "timestamp_to" current (#444)
- `SensorAlarm.create_or_lengthen()` reads and writes through Core statements, so an alarm
  created earlier in the same batch is seen by the next one without relying on autoflush, and
  ignores alarms older than the row's "timestamp_to" (out-of-order delivery) (#444)
- The sensors skeleton orders measures as temperature, humidity, light, TVOC, dew point,
  absolute moisture, then moisture (#410)
- Email templates reworked to match the frontend's identity: the "Ouranos - Gaia control" brand
  over a single sheet (kicker, Garamond title, hairlines, a footer bar stating the token's
  validity), a button naming the act, and the token in a labelled block; the invitation's
  manual link now points to "/auth/register", where the frontend's token gate lives (#454)
- Emails are only sent when the "email" service is enabled; `Service` is now cached (#458)
- `CRUDMixin` split into three layers: `CRUDMixin` keeps the plain CRUD methods, without
  lookup keys nor single-row `update()`/`delete()` but with a new `delete_multiple()` by
  primary key; `UniqueCRUDMixin` adds the lookup keys and the single-row methods they
  guard; `UpsertCRUDMixin` adds the "on conflict" machinery, `get_or_create()` and
  `update_or_create()`. The existing models now use `UpsertCRUDMixin` (#484)
- Archiving: `ArchivableMixin` is a base mixin, combined with a CRUD mixin by each archivable
  model; `Archiver` deletes the archived rows batch by batch rather than all at the end, and
  never archives an unsolved warning (#481, #485, #489)
- **Breaking**: archiving is disabled for a data type whose `SENSOR_ARCHIVING_PERIOD`,
  `ACTUATOR_ARCHIVING_PERIOD` or `WARNING_ARCHIVING_PERIOD` is unset, rather than defaulting
  to 180 days (#490)
- `ActuatorRecordArchive` drops its "actuator_uid" column (with its migration script), which
  `ActuatorRecord` never had (#486)
- "join_room_ack" and "leave_room_ack" Socket.IO events now carry the "room", and a failure
  with its "reason" when joining or leaving fails (#475, #491)
- An engine's ecosystems are only returned if they are still in its config (#463)
- The ecosystem "turn_actuator" route's payload gains a "level" (0 to 100, defaults to 100)
  and requires a non-negative "countdown"; the weather event update payload requires a
  positive "duration" and a "level" between 0 and 100 (#500)
- Admins can see, edit and delete other users' private calendar events (#504)
- The "/{...}/image_info" routes round their time window to the second rather than to 10 s,
  which could hide pictures, as they are sent every minute and overwrite each other (#434)
- A warning is logged when the web server runs with several workers, as the user cache, and
  thus session revocation, is per worker (#420); the "memory-based dispatcher" warning is
  also raised when a functionality uses workers (#467)
- `ImmutableDict` also refuses `del`, `update()` and `pop()` (#498)
- `PluginManager` no longer loads the entry points of omitted plugins, and lets a plugin's
  loading error propagate (#421)
- Plugin execution moved out of `Plugin` into a `PluginExecutor`, in process or in
  subprocesses (#423); the subprocess one stops its workers concurrently rather than one
  after the other, so stopping takes up to 5 s instead of 5 s per worker (#509)
- `Ouranos` is now a `Host` running every registered plugin instead of a `Functionality`
  managing them, and `Plugin.run_as_standalone()` runs its plugin on a `Host` too: a
  standalone plugin now initializes the database in the parent process before spawning
  its workers. `PluginManager.start_plugins()`/`stop_plugins()` are removed (their
  all-or-none startup and reverse-order shutdown moved to `Host`), as are
  `Functionality.init_the_db()`/`init_the_scheduler()`, replaced by
  `acquire_common_resources()`/`release_common_resources()` (#511)
- The app, the CLI and the tests set up the database through a single `setup_db()`, and the
  `database.init` functions take the `db` explicitly; "fill-db" accepts `--config-profile`
  and `--config-override`, and a database without revision now fails with the commands
  to initialize it (#514)
- FastAPI's own `JSONResponse` replaces the custom one (#480)

### Removed
- The reloading web server and its `WEB_SERVER_RELOAD` config parameter: it watched no core
  file and could not run (#510)

### Fixed
- Sensor alarms were overridden by the last `sensors_data` event received before they were
  logged, so with several engines only the last one's alarms ever reached the DB; they now
  accumulate in a set until logged (#444)
- `User.confirm()` bypassed `User.update()`, leaving a stale entry in the `User` cache, so a
  freshly confirmed user kept being seen as unconfirmed; its "active" check was also restored,
  and the `RuntimeError` it raises is now caught by the "confirm_account" route, which answers
  400 instead of 500 (#415)
- Nested `scoped_session()` in `ClientEvents.on_user_heartbeat()` (#415)
- `session.commit()` called inside a `scoped_session()` by some `GaiaEvents` handlers and
  model helpers (#482)
- Mismatch between the "users" columns generated by SQLAlchemy and by the migration script:
  the timestamp columns lacked a `server_default` (#415)
- The "connection_date" migration failed on SQLite, which needs the table recreated to insert
  a column at a given position (#455)
- `SessionInfo.is_fresh` inverted its check, so only stale sessions were fresh (#414)
- "password_reset_token" route issued tokens valid for `REGISTRATION_TOKEN_VALIDITY` rather
  than `PASSWORD_RESET_TOKEN_VALIDITY` (#469)
- `User.get_multiple()` filtered the registration time on a non-existent column (#472)
- Email plain-text alternative: a link carrying any attribute besides "href" lost its URL and
  left a stale entry on the link stack; the source's line wrapping also leaked into the text
  (#454)
- Third-party libraries' logs were silenced, as their loggers mostly exist before the logging
  configuration is applied; their warnings and errors now reach the same outputs as Ouranos'
  own logs, while debug mode still only lowers the level of Ouranos' and Uvicorn's loggers
  (#465)
- "On conflict do update" only updates the columns supplied, so a column default (e.g. a
  creation timestamp) is no longer recomputed on every conflict, while the columns with an
  `onupdate=` are refreshed (#439, #445)
- `CachedCRUDMixin` cached instances stayed attached to the session that loaded them (#457)
- Passing `[]` to the hardware's "measures"/"groups" or to the plant's "hardware" was
  ignored instead of detaching every previously attached one (#501)
- Attaching hardware to a plant left the hardware's cache stale (#503)
- The ecosystems routes built their `HTTPException`s without raising them, answering a
  success on failure (#440); the wiki upload routes turned their 413 into a 422, and a few
  error `detail`s were tuples (#507)
- `GaiaEvents` emitted "initialization_ack" to every engine rather than to the sender (#468),
  and a "turn_actuator" order for an unknown ecosystem to every engine (#417)
- AMQP queues are durable, as RabbitMQ 4.3 refuses non-durable, non-exclusive ones (#428)
- `create_sio_manager()` built a "redis://" URL for an AMQP backend (#466)
- Plugin routes were added with `add_route()` rather than `add_api_route()` (#479)
- The CLI's plugin subcommands always crashed, as `get_command()` read the plugins before
  they were registered (#502)
- `PathsHelper` raised a `TypeError` instead of a `ValueError` for an unset directory (#499)
- `WIKI_DIR` read `OURANOS_STATIC_DIR` rather than `OURANOS_WIKI_DIR` (#508)
- A query datetime without timezone made the time-window routes answer 500; such datetimes
  are now read as UTC (#506)
- Updating or deleting a private calendar event answered 404 to its owner (#504)
- `--config-override` crashed on a value containing "=" or on a missing "=" (#514)
- The start script wrote `uv run`'s PID rather than Ouranos' to the PID file, and the start
  and stop scripts missed an instance still starting up (#404)
- `Plugin.executor` stayed reachable after `Plugin.shutdown()` or a failed `Plugin.startup()`,
  and an in-process functionality failing to start was kept by its executor; the plugin's
  running state is now derived from its executor (#495)
- `Aggregator.shutdown()` stopped its components in a single `try`, so one failing to stop
  left the following ones, including the dispatchers, running; each is now stopped on its own
  and its failure logged. Its `log_sensors_data_and_alarms` job is now removed too (#496)
- A plugin failing to start left the plugins started before it running until the process was
  killed; Ouranos now starts its plugins all or none, stopping those already started before
  raising, and releases the shared resources. Plugins are stopped in reverse order, and one
  failing to stop no longer leaves the following ones running (#493, #497, #511)
- Every `PluginManager()` call re-ran its `__init__` and wiped the registered plugins of the
  shared instance; `PluginManager` now uses the new `core.utils.SingletonMeta`, and its callers
  only register the plugins if it has not been done yet (#505)
- The multi-worker web server never served since the `uvicorn` 0.51 bump: its workers
  started without the config, so creating the app failed and they were respawned forever,
  while its startup still succeeded. Its supervisor also blocked the event loop; it now runs
  in a thread, its startup waits for a worker to listen, and its socket is closed when
  stopped (#452, #510)
- A multi-worker web server whose app failed to be created kept respawning its workers
  forever, and its failed startup left uvicorn's supervisor running, so Ouranos hung at exit;
  such a worker now exits with uvicorn's `STARTUP_FAILURE`, and a failed startup stops the
  supervisor. A same-process web server failing to start no longer waits forever (#513)

### Security
- Resetting a password or deleting a user now revokes every session token issued beforehand;
  until now a leaked session cookie stayed usable for its full 31-day lifetime (#415)
- `is_fresh()` now raises instead of returning a boolean: as a `Depends()` route dependency its
  return value is discarded, so it would have gated nothing (#415)
- Session tokens now carry a "session" subject, and tokens without it or missing a required
  field are rejected; until now a password reset or confirmation token was accepted as a
  session cookie that was always fresh and could not be revoked. Existing sessions are
  invalidated, so every user has to log in again once (#470)
- Updating a service's status requires an admin (#409)
- Ecosystem and camera uids of uploaded pictures are validated, so they can't write files
  outside the camera directory (#418)
- Logging in as an unknown user or one without password still verifies a dummy hash, so
  response times don't reveal which accounts exist (#419)

### Development
- Sandbox script (`scripts/utils/sandbox.sh`) to run the install and update scripts in an
  isolated throwaway environment, leaving the real install, `~/.profile` and systemd
  untouched; it tests the working tree, uncommitted changes included (#407, #408)
- CI workflow running the installation and update scripts in the sandbox (#424)
- `ty` type checking extended to every module, `ruff` and `ty` pinned (#406, #430, #432, #433,
  #449, #451, #453)
- Testing dependencies moved from `optional-dependencies` to `dependency-groups` (#426)
- Tests covering the `user_session` module, session revocation, session extension and
  session refreshing (#415); `{Cached}CRUDMixin` coverage increased (#462); `ServicesEnabled`
  class fixture made parametrizable (#459); `SystemAware` stamps its record when it runs
  (#473)
- `AGENTS.md` (#487)
- Readme: how a plugin declares itself in the master `pyproject.toml` and how to disable one;
  the development instructions now use `--group` following the move to `dependency-groups`
  (#429); badges and the chatbot plugin's address (#447, #474)
- Internal cleanups (#471, #516); `.gitignore` and copyright years updated (#405, #448,
  #456)
- `aio_pika` (8.3), `cachetools` (7.0), `cryptography` (50.0), `numpy` (2.5), `psutil` (7.1),
  `pydantic` (2.14), `pytest` (9.1), `python_multipart` (0.0.31), `SQLAlchemy` (2.1) and
  `uvicorn` (0.51) bumped, as were `event-dispatcher` and `gaia-validators` (#411, #416,
  #431, #446, #452, #461, #464, #476, #477, #478, #488, #492, #494)

---

## 0.11.0 — 2026-07-21

### Added
- `HardwareGroup` model introduced; measures and actuator groups linked to `Hardware`
  and `EnvironmentParameter`, reflecting Gaia's group-based actuator control (#304, #305, #307)
- "active" field added to the `Hardware` table (#326)
- "weather" aggregator event added (#300)
- `CRUDMixin.get_or_create()` (#301)
- `StmtModifier` to easily modify `CRUDMixin._get{_multiple}()` requests (#361)
- "measure" and "groups" info exposed on the environment-parameters and hardware routes (#306)
- "recent_picture" field on `Ecosystem.get_functionalities()` and the routes using it (#362)
- `Plugin.check_requirements()` override hook for startup validation (#313)
- `Plugin.create_run_command()` for defining custom CLI commands and groups (#310)
- CLI command to fill the database with the default tables (#332)
- "unsafe" option on the installation / update scripts to use the latest development version (#335)
- Gaia–Ouranos contract version negotiated at engine registration (`GAIA_CONTRACT`);
  engines whose contract does not match are refused through the `registration_ack` status (#399)
- Client-facing contract versions (`REST_CONTRACT`, `SOCKETIO_CONTRACT`) exposed on the
  `/app/contracts` route and checked against plugins at registration; incompatible plugins
  are skipped with a `ContractVersionError` (#401)
- SocketIO contract checked at connection: a client advertising an incompatible
  `socketio_contract` is refused with a structured reason (#402)

### Changed
- `Plugin` setup and startup improved; `Functionality` and `Plugin` runtime made more robust (#342, #345, #369)
- `Archiver` reworked and coupled more tightly with DB models to prevent drift (#346)
- `Aggregator`, `WebServer`, and `FileServer` lifecycles improved (#371, #372, #376)
- `GaiaEvents` and `CRUDMixin` cleaned up and improved; gaia-related models cleaned up (#348, #349, #354)
- Caching and cache invalidation improved in `CachedCrudMixin`; caching utilities documented (#350, #368)
- DB revision checked at startup; `check_db_revision()` is launch-directory-agnostic (#318, #324)
- DB migration handling eased; table creation managed through SQLAlchemy during updates (#317, #338)
- DB connections recycled after 1 hour (#364)
- Sensor data queries optimised when a `TimeWindow` is provided; composite index added
  on `sensor_records` ("sensor_uid", "timestamp") (#398)
- Non-specific "image_info" routes support time-window narrowing (#363)
- Non-specific environment-parameters routes take a list of `gv.ClimateParameter`
  rather than a single string (#309)
- Unique constraints added to all `Association{...}` tables (#298)
- Exception handling improved, logging clutter reduced, and shutdown made cleaner (#323)
- Full error traceback no longer printed when running a `Plugin` in production (#314)
- Dummy plugins no longer exposed outside development and testing builds (#311)
- Installation and update scripts simplified, hardened, and made more resilient (#344, #360)
- `update.sh` also upgrades the database (#322)

### Fixed
- Race conditions in `update_or_create()` handled more robustly (#303)
- Edge cases in `CRUDMixin` (#367)
- Various bugs in `SkyWatcher` (#353)
- `Optional` types better handled by `sqlalchemy_to_pydantic` (#312)
- `HTTPException` properly raised after failed CRUD requests in the hardware routes (#392)
- "turn_light" and "manage_ecosystem" client events (#395)
- Several bugs in the update script (#370)

### Security
- Socket.IO authentication moved to connect time; actuation handlers secured (#396)
- Regular users can no longer join or leave the "admin" room through the room events (#393, #394)

### Development
- `event-dispatcher` (0.8.0), `gaia-validators` (0.11.0), `sqlalchemy-wrapper` (0.5.0),
  and `pytest-asyncio` (1.4) bumped
- `uv` adopted for virtual environment and package management; GitHub workflows updated (#331, #343)
- `ty` type checking added for the `core/database` modules (#366)
- Extensive test coverage added across routes (auth, users, hardware, sensors, engines,
  ecosystems, calendar, weather, wiki, warnings, system, services), events, and
  functionalities; `TestAggregator` and `TestWebServer` harnesses introduced

---

## 0.10.0 — 2025-10-14

### Added
- "plants" event to communicate plant health data to Gaia
- `start.sh` "foreground" option for systemd integration
- Per-package update scripts supported in `install.sh` / `update.sh`

### Changed
- "management" route now returns actuator status based on whether at least one actuator
  is active
- `Hardware`, `Measure`, and `Plant` guaranteed not to be linked more than once
- All `Mapped[datetime]` columns use `UtcDateTime`
- DB models using `_lookup_keys` now have a unique constraint
- `CRUDMixin`: `_on_conflict_do` support in `create` / `create_multiple` subclasses;
  `_get_lookup_keys` and related helpers moved from `Base` to `CRUDMixin`
- Log failures during `on_buffered_*` events; log to file enabled by default
- `install.sh` and `update.sh` hardened: can be sourced without executing `main`;
  option to update only ouranos-core

### Removed
- "environmental_parameters" event (deprecated since 0.9.0)

### Fixed
- Hardware update CRUD request and payload validation issues
- Hardware-plant relationship serialization

### Development
- QC workflow added to CI/CD; tests reorganised into classes

---

## 0.9.0 — 2025-05-25

### Added
- Email service: account confirmation, password reset, and mail-sending module
- Wiki improvements: article versions stored as compact diffs; tags on topics, articles
  and pictures; slugified URLs; picture tagging and file upload; `WikiArticlePicture`
  made a `CRUDMixin`
- "buffered_health_data" event; health data treated as a special case of sensor data;
  routes and payload adapted for frontend consumption
- User "last_seen" tracking; `/auth/refresh_session` route
- Calendar events: time-window search, public events, visibility restricted for
  anonymous users, 31-day default window
- `SQLIntEnum` for storing `IntEnum` as integers in the database
- Python 3.13 added to the test matrix

### Changed
- "environmental_parameters" aggregator event split into three focused events; emitted
  at each weather update
- `GaiaEvents.validate_payload` converted to a decorator
- Session cookie expiration extended; "remember me" no longer uses a session-limited token
- User deletion is now a soft delete; `User.get_by` supports AND / OR clauses
- `CRUDMixin.create()` gains `_on_conflict_do` argument; `RecordMixin` made a subclass
  of `CRUDMixin`; `offset`, `limit` and `order_by` added to `CRUDMixin.get()`
- "memory" database replaced by a SQLite-backed "transient" database
- Engine / ecosystem connection timeout increased to 60 seconds
- FastAPI bumped to 0.115, pydantic to 2.11, uvicorn to 0.34

### Removed
- Jinja2 removed from requirements

---

## 0.8.0 — 2024-11-28

### Added
- Camera pictures received from Gaia stored via a Starlette-based file server;
  compressed image support in "picture_arrays" event; bulk upload route added
- Basic wiki (static file delivery)
- Socket.IO join/leave room events
- `aioCache`: SQLite-backed cache for sharing data across processes
- User caching; fast paths for recent `Engine`s and `Ecosystem`s
- Brotli response compression

### Changed
- `StreamGaiaEvents` merged back into `GaiaEvents`
- `CRUDMixin` made more robust: `lookup_keys` validation enforced, tolerant to primary
  keys other than "uid"; primary key consistency improved across tables
- System data format uniformized between API and WebSocket
- `anyio.Path` replaces `pathlib.Path` for non-blocking file I/O
- Python 3.9 and 3.10 support dropped

### Removed
- `asyncache` dependency

### Development
- GitHub Actions test suite with coverage added; in-memory SQLite used in tests

---

## 0.7.1 — 2024-07-31

### Added
- Alembic for database migrations

### Changed
- Events updated to match Gaia's updated registration handshake
- `User.can()` method moved from `User` to `UserMixin`

---

## 0.7.0 — 2024-07-29

First release with a structured PR workflow.

### Added
- Gaia sensor alarms caught and logged
- "ecosystems heartbeat" and "place_list" events
- Route added to query actuator history; actuator records logged on each
  "actuators_data" event
- Calendar events routes
- Gaia warnings creation, update, and filtering routes
- User management routes: get, update, soft delete / deactivate
- `lighting_method` field on ecosystem creation and update routes
- `ConfigHelper` and `PathsHelper` for robust config and path resolution
- SQLite-based logger

### Changed
- "actuators_data" event replaces deprecated "actuator_data"
- `registration_required` decorator re-registers unrecognised engines automatically;
  Gaia registration handshake improved; TTL added to "registration_ack" message
- User information embedded in registration tokens; registration API returns same
  payload as login
- Frontend address auto-added to allowed API origins
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

### Added
- "buffered_sensors_data" event: logs sensor data buffered by Gaia during connection
  outages
- Absolute humidity and dew point measures supported
- Admin overview page; server info streamed to admin clients

### Changed
- CORS: Vite and Node dev servers added as allowed origins in development mode

### Removed
- `gaiaAggregator` and legacy `gaiaConfig` modules

---

## 0.5.2

Project renamed from gaiaWeb to **Ouranos**. This release also marks the beginning of
the frontend split: the Vue-based UI is extracted into a separate project, and
ouranos-core becomes a pure backend API server.

### Added
- Flask-RESTX: API endpoints reorganised into namespaces under `src/app/routes/`
  (app, auth, gaia, weather, system); dedicated `src/api/` layer separates business
  logic from route definitions
- Event dispatcher integrated: inter-component communication is now event-driven;
  `configure_dispatcher()` called at startup in the new `main.py` entry point
- Fine-grained permission model: `Permission` flags (VIEW, EDIT, OPERATE, ADMIN) and
  `Role` model with per-route `@permission_required` decorator
- `src/consts.py` for shared constants
- Flask-CORS and marshmallow

### Changed
- Database models reorganised into `src/database/models/` with dedicated files
  (`app.py`, `gaia.py`, `archives.py`, `system.py`) replacing a single models module
- WebSocket event handlers moved to `src/app/events/` (`clients.py`, `gaia.py`)
- Redis caching refactored from `src/dataspace/` to `src/redis_cache.py`; TTL-based
  in-memory caches added for frequently accessed ecosystem data (`cachetools.TTLCache`)
- Config env var renamed from `GAIA_CONFIG` to `OURANOS_PROFILE`

### Removed
- Flask-Migrate, Flask-Mail, Flask-WTF

---

## 0.5.1

### Added
- License file

### Changed
- Minor configuration adjustments; no structural changes

---

## 0.5.0

First standalone gaiaWeb release. Gaia and Ouranos were previously a single combined
project (versions 0.0.1–0.4.0); 0.5.0 is the split, taking the `gaiaWeb` part as its
own project.

### Added
- Flask application factory (`create_app`) with configuration profiles for development,
  testing, and production
- SQLAlchemy ORM replaces the `gaiaDatabase` SQL abstraction; multiple database binds:
  `db_app.db` (users and application data), `db_ecosystems.db`, `db_archive.db`
- Flask-Login for session-based user authentication
- Flask-SocketIO for real-time WebSocket communication with Gaia clients
- Flask-Migrate (Alembic) for database schema migrations
- Services architecture: `archiver`, `weather`, `system_monitor`, `notifications`,
  `telegram_chat_bot`, `daily_recap`, `sun_times`, `webcam`, `calendar` — each service
  manages its own lifecycle and shares the scheduler
- Redis-based data caching layer (`src/dataspace/`)
- Flask-Mail for email notifications; Flask-WTF for form validation
- Blueprints: `auth`, `admin`, `main`, `api`, `errors`
- Wiki section

---

*Versions 0.1.0–0.4.0 are from the combined Gaia + Ouranos era. Only the web server
(gaiaWeb) parts are described below.*

---

## 0.4.0 — March 2020

### Added
- Flask blueprints: `auth`, `core`, `errors`
- User authentication: registration, login, logout with password hashing (werkzeug)
- APScheduler background jobs: sensor data logged every 10 min, plant data every 15 min
- System resource monitoring (CPU / RAM / disk via `psutil`), logged every 5 min
- Multi-ecosystem support in web routes: `/environment/<ecosystem>`,
  `/plants/<ecosystem>`
- Routes: `/home`, `/weather`, `/warning`, `/care/*`

### Changed
- Context processors inject user, ecosystems, plants, and warnings into every template

---

## 0.3.0 — February 2020

### Added
- gaiaWeb established as a dedicated module, separated from gaiaEngine
- Routes expanded: `/sensors/overview`, `/sensors/<environment>`, `/sensors/settings`,
  `/weather`
- Multi-ecosystem support; per-environment data visualisation with temporal history
  passed to templates

### Changed
- YAML cache files used as data source (replaces direct MySQL queries in routes)

---

## 0.2.0 — December 2019

### Changed
- Web server reorganised into the `Website/GaiaWeb/` directory; no significant
  web-specific changes

---

## 0.1.0 — September 2019

Initial version, a single combined Gaia + Ouranos project:

### Added
- Flask web app (`Hello.py`) with direct MySQL queries (MySQLdb)
- Routes: `/home`, `/environment`, `/plants`, `/care/*`, `/settings`, `/about`
