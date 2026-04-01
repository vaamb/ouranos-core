Ouranos
=======

Ouranos is the companion server for [Gaia](https://github.com/vaamb/gaia),
the plant environment automation client. It aggregates sensor data from one or
more Gaia instances, archives it, exposes a REST + WebSocket API, and serves
as the backend for the [web UI](https://github.com/vaamb/ouranos-frontend) and
[Telegram bot](https://gitlab.com/eupla/ouranos-chatbot).

Part of the [gaia-ouranos](https://github.com/vaamb/gaia-ouranos) ecosystem.

---

Features
--------

**Aggregator**
- Receives sensor data, actuator states, and hardware info from Gaia instances
  in real time via AMQP (RabbitMQ) or Redis
- Archives data from recent tables to long-term storage on a configurable schedule
- Fetches weather forecasts and sunrise/sunset times from external APIs
- Hosts a dedicated file server for camera image uploads from Gaia

**Web API** (FastAPI + Socket.IO)
- Ecosystem and hardware management — create, configure, and control Gaia
  ecosystems and their hardware remotely
- Sensor data — current readings and historic queries per ecosystem or sensor
- Actuator control — send commands and retrieve status and history
- Warnings — surface and manage sensor alarms
- Services — weather forecasts, calendar, wiki
- System monitor — CPU, RAM, and disk usage
- Authentication — JWT-based with role-based access control (admin, operator, user)
- OpenAPI docs at `/api/docs`

**Plugin SDK**
- Extend Ouranos with custom `Functionality` subclasses that hook into the
  async lifecycle (initialize → startup → shutdown)
- Plugins can expose FastAPI routes, CLI commands, and background services
- Plugins run in-process or as independent subprocesses via the multiprocess
  spawn API

---

Requirements
------------

- Python 3.11+
- `uv` — used for dependency management and running the app
- A message broker: RabbitMQ or Redis (optional — in-memory for single-instance)
- systemd (optional — for running as a service)

---

Installation
------------

Copy the install script from the `scripts/` directory and run it in the
directory where you want to install Ouranos:

```bash
bash install.sh
```

The script clones the repository, sets up a `uv`-managed virtual environment,
installs all dependencies, and optionally configures a systemd service.

After installation, initialise the database:

```bash
source ~/.profile
ouranos fill-db --no-check-revision
alembic stamp head
```

---

Running
-------

If installed as a systemd service:

```bash
sudo systemctl start ouranos.service
sudo systemctl enable ouranos.service   # start on boot
```

Using the CLI directly:

```bash
ouranos start
ouranos stop
ouranos restart
ouranos status
```

By default, Ouranos runs the web server, aggregator, and all installed plugins
in a single process. Individual components can be run separately by passing the
appropriate flags — see `ouranos --help` for details.

---

Configuration
-------------

Ouranos is configured via a `config.py` file placed in `$OURANOS_DIR`. It must
define a `DEFAULT_CONFIG` variable pointing to a class that subclasses
`BaseConfig` (and any plugin configs, e.g. `FrontendConfig`, `ChatbotConfig`):

```python
from ouranos.core.config.base import BaseConfig
from ouranos_frontend.config import Config as FrontendConfig

class Config(FrontendConfig, BaseConfig):
    DEVELOPMENT = True

    GAIA_COMMUNICATION_URL = "amqp://localhost"
    HOME_COORDINATES = (59.51, 17.38)
    OPEN_WEATHER_MAP_API_KEY = "your_key_here"

DEFAULT_CONFIG = Config
```

All settings can also be provided via environment variables. Key settings:

| Setting                    | Env variable                            | Description                                               |
|----------------------------|-----------------------------------------|-----------------------------------------------------------|
| `SECRET_KEY`               | `OURANOS_SECRET_KEY`                    | JWT signing key                                           |
| `GAIA_COMMUNICATION_URL`   | `GAIA_COMMUNICATION_URL`                | Broker URL for Gaia (`amqp://` or `redis://`)             |
| `DISPATCHER_URL`           | `OURANOS_DISPATCHER_URL`                | Internal dispatcher (`memory://` or `amqp://`)            |
| `SIO_MANAGER_URL`          | `OURANOS_SIO_MANAGER_URL`               | Socket.IO manager (`memory://`, `redis://`, or `amqp://`) |
| `API_HOST` / `API_PORT`    | `OURANOS_API_HOST` / `OURANOS_API_PORT` | Web server bind address (default: `127.0.0.1:5000`)       |
| `FRONTEND_URL`             | `OURANOS_FRONTEND_URL`                  | Allowed frontend origin (CORS)                            |
| `DB_DIR`                   | `OURANOS_DB_DIR`                        | Directory for SQLite databases                            |
| `HOME_COORDINATES`         | `HOME_COORDINATES`                      | `(lat, lon)` used for sunrise/sunset and weather          |
| `OPEN_WEATHER_MAP_API_KEY` | `DARKSKY_API_KEY`                       | API key for weather forecasts                             |
| `PLUGINS_OMITTED`          | `OURANOS_PLUGINS_OMITTED`               | Comma-separated list of plugins to skip                   |
| `MAIL_USERNAME`            | `OURANOS_MAIL_ADDRESS`                  | SMTP username for email notifications                     |

---

Development
-----------

Clone the repository and install dependencies with test extras:

```bash
git clone https://github.com/vaamb/ouranos-core.git
cd ouranos-core
uv sync --extra test
```

Run the test suite:

```bash
uv run pytest tests/ -v
```

Lint:

```bash
uvx ruff check .
```

---

Tech stack
----------

- Python 3.11+ · FastAPI · Uvicorn · asyncio
- SQLAlchemy 2.0 (async) · Alembic · aiosqlite
- python-socketio · aio-pika · APScheduler
- PyJWT · argon2-cffi
- numpy · OpenCV (plant health image analysis)
- [event-dispatcher](https://github.com/vaamb/event-dispatcher) ·
  [gaia-validators](https://github.com/vaamb/gaia-validators) ·
  [sqlalchemy-wrapper](https://github.com/vaamb/sqlalchemy-wrapper)
- uv · ruff · pytest · pytest-asyncio · coverage
- GitHub Actions CI: lint + tests across Python 3.11 / 3.12 / 3.13

---

Status
------

Active. Running in production at home since 2020. The core data flow is stable;
APIs may still change. Requires at least one running Gaia instance for the
aggregator to receive data, but the web server and services run independently.
