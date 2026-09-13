import asyncio
import datetime as dt
import logging
import logging.config
import sys

import pytest

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.models.logging import AccessLog, BaseLog, LogLevel
from ouranos.core.database.models.utils import TimeWindow
from ouranos.core.logging import configure_logging, DBHandler


def _make_record(
        *,
        level: int = logging.INFO,
        name: str = "ouranos.test",
        msg: str = "a log message",
        exc_info=None,
) -> logging.LogRecord:
    return logging.LogRecord(
        name=name,
        level=level,
        pathname=__file__,
        lineno=1,
        msg=msg,
        args=(),
        exc_info=exc_info,
        func="test_func",
    )


# All the CRUD/filtering behaviour lives on the abstract `BaseLogRecord` and
# is exercised here through `BaseLog`, one of its two concrete tables;
# `TestSeparateTables` below is what actually checks `BaseLog`/`AccessLog`
# are independent.


@pytest.mark.asyncio
class TestLogRecordCreateAndGet:
    async def test_create_and_get_multiple(self, db: AsyncSQLAlchemyWrapper):
        record = _make_record(level=logging.WARNING, msg="disk almost full")
        async with db.scoped_session() as session:
            await BaseLog.create(session, record)
            stored = await BaseLog.get_multiple(session)

        assert len(stored) == 1
        entry = stored[0]
        assert entry.level == LogLevel.WARNING
        assert entry.logger_name == "ouranos.test"
        assert entry.func_name == "test_func"
        assert entry.message == "disk almost full"
        assert entry.traceback is None


@pytest.mark.asyncio
class TestLogRecordTraceback:
    async def test_create_stores_traceback(self, db: AsyncSQLAlchemyWrapper):
        try:
            raise ValueError("boom")
        except ValueError:
            exc_info = sys.exc_info()
        record = _make_record(level=logging.ERROR, exc_info=exc_info)

        async with db.scoped_session() as session:
            await BaseLog.create(session, record)
            stored = await BaseLog.get_multiple(session)

        assert len(stored) == 1
        assert "ValueError: boom" in stored[0].traceback

    async def test_create_without_exc_info_has_no_traceback(
            self, db: AsyncSQLAlchemyWrapper):
        record = _make_record(level=logging.INFO)

        async with db.scoped_session() as session:
            await BaseLog.create(session, record)
            stored = await BaseLog.get_multiple(session)

        assert stored[0].traceback is None


@pytest.mark.asyncio
class TestLogRecordLevelFiltering:
    async def test_get_multiple_filters_by_level_range(
            self, db: AsyncSQLAlchemyWrapper):
        async with db.scoped_session() as session:
            await BaseLog.create(session, _make_record(level=logging.DEBUG, msg="dbg"))
            await BaseLog.create(session, _make_record(level=logging.INFO, msg="info"))
            await BaseLog.create(session, _make_record(level=logging.WARNING, msg="warn"))
            await BaseLog.create(session, _make_record(level=logging.ERROR, msg="err"))

            debug_only = await BaseLog.get_multiple(session, level_max=LogLevel.DEBUG)
            warning_and_up = await BaseLog.get_multiple(session, level_min=LogLevel.WARNING)

        assert [r.message for r in debug_only] == ["dbg"]
        assert {r.message for r in warning_and_up} == {"warn", "err"}


@pytest.mark.asyncio
class TestLogRecordOrdering:
    async def test_get_multiple_orders_newest_first(
            self, db: AsyncSQLAlchemyWrapper):
        now = dt.datetime.now(dt.timezone.utc)
        async with db.scoped_session() as session:
            for offset, msg in ((20, "oldest"), (0, "newest"), (10, "middle")):
                record = _make_record(msg=msg)
                record.created = (now - dt.timedelta(seconds=offset)).timestamp()
                await BaseLog.create(session, record)

            stored = await BaseLog.get_multiple(session)

        assert [r.message for r in stored] == ["newest", "middle", "oldest"]


@pytest.mark.asyncio
class TestLogRecordTimeWindow:
    async def test_get_multiple_time_window(self, db: AsyncSQLAlchemyWrapper):
        now = dt.datetime.now(dt.timezone.utc)
        async with db.scoped_session() as session:
            too_old = _make_record(msg="too_old")
            too_old.created = (now - dt.timedelta(hours=2)).timestamp()
            await BaseLog.create(session, too_old)

            in_window = _make_record(msg="in_window")
            in_window.created = (now - dt.timedelta(minutes=30)).timestamp()
            await BaseLog.create(session, in_window)

            windowed = await BaseLog.get_multiple(
                session,
                time_window=TimeWindow(start=now - dt.timedelta(hours=1), end=now),
            )

        assert [r.message for r in windowed] == ["in_window"]


@pytest.mark.asyncio
class TestLogRecordPagination:
    async def test_get_multiple_pagination(self, db: AsyncSQLAlchemyWrapper):
        now = dt.datetime.now(dt.timezone.utc)
        async with db.scoped_session() as session:
            for i in range(5):
                record = _make_record(msg=f"msg-{i}")
                record.created = (now - dt.timedelta(seconds=i)).timestamp()
                await BaseLog.create(session, record)

            page_1 = await BaseLog.get_multiple(session, page=1, per_page=2)
            page_2 = await BaseLog.get_multiple(session, page=2, per_page=2)

        # Newest first, so page 1 holds offsets 0-1 and page 2 holds 2-3
        assert [r.message for r in page_1] == ["msg-0", "msg-1"]
        assert [r.message for r in page_2] == ["msg-2", "msg-3"]


@pytest.mark.asyncio
class TestSeparateTables:
    async def test_base_log_and_access_log_are_independent_tables(
            self, db: AsyncSQLAlchemyWrapper):
        """The whole point of `BaseLog`/`AccessLog`: each is its own table,
        with its own index (`declared_attr` on `BaseLogRecord.__table_args__`
        gives each concrete subclass its own `Index` instance, named after
        its own table -- reusing one `Index` object across tables raises
        `ArgumentError`, which is what this guards against).
        """
        async with db.scoped_session() as session:
            await BaseLog.create(session, _make_record(msg="base entry"))
            await AccessLog.create(session, _make_record(msg="access entry"))

            base_rows = await BaseLog.get_multiple(session)
            access_rows = await AccessLog.get_multiple(session)

        assert [r.message for r in base_rows] == ["base entry"]
        assert [r.message for r in access_rows] == ["access entry"]
        assert BaseLog.__tablename__ != AccessLog.__tablename__


def test_dbhandler_requires_a_table_model():
    with pytest.raises(ValueError):
        DBHandler(None)


def test_dbhandler_emit_without_running_loop_does_not_raise(capsys):
    """`emit()` can be called before the app's event loop exists (e.g. a log
    statement during synchronous startup); it must report the miss and return
    rather than raise.
    """
    handler = DBHandler(BaseLog)
    record = _make_record(msg="log emitted before the loop started")

    handler.emit(record)

    assert handler._loop is None
    captured = capsys.readouterr()
    assert "log emitted before the loop started" in captured.err


@pytest.mark.asyncio
class TestDBHandlerEmit:
    async def test_emit_writes_record_via_the_running_loop(
            self, db: AsyncSQLAlchemyWrapper):
        """`emit()` is sync; the actual DB write is handed off to the running
        loop via `run_coroutine_threadsafe`. Give it a couple of loop
        iterations to run before checking the DB.
        """
        handler = DBHandler(BaseLog)
        record = _make_record(level=logging.ERROR, msg="handled via emit()")

        handler.emit(record)
        await asyncio.sleep(0.1)

        async with db.scoped_session() as session:
            stored = await BaseLog.get_multiple(session)

        assert [r.message for r in stored] == ["handled via emit()"]
        assert handler._loop is asyncio.get_running_loop()


@pytest.mark.asyncio
class TestDBHandlerSeparateTables:
    async def test_two_handlers_write_to_their_own_table(
            self, db: AsyncSQLAlchemyWrapper):
        base_handler = DBHandler(BaseLog)
        access_handler = DBHandler(AccessLog)

        # `_log_record` (what `emit()` schedules via `run_coroutine_threadsafe`)
        # awaited directly, deterministically, rather than via `emit()` + a
        # fixed sleep: two handlers each independently racing their own
        # `_create_table()`/`create_all()` on first use made a fixed sleep
        # flaky. `emit()`'s scheduling itself is already covered by
        # `TestDBHandlerEmit`.
        await base_handler._log_record(_make_record(msg="from base handler"))
        await access_handler._log_record(_make_record(msg="from access handler"))

        async with db.scoped_session() as session:
            base_rows = await BaseLog.get_multiple(session)
            access_rows = await AccessLog.get_multiple(session)

        assert [r.message for r in base_rows] == ["from base handler"]
        assert [r.message for r in access_rows] == ["from access handler"]


@pytest.mark.parametrize(
    "log_to_stdout,log_to_file,log_to_db",
    [
        (True, True, True),
        (True, True, False),
        (False, False, True),
        (True, False, True),
        (False, True, False),
        (False, False, False),
    ],
)
def test_configure_logging_does_not_raise_for_any_flag_combination(
        tmp_path, log_to_stdout, log_to_file, log_to_db):
    """Regression test: `configure_logging` previously crashed unconditionally
    (a `db_handler` dict carrying a stale `table_model: None` placeholder
    got instantiated by `dictConfig` regardless of `LOG_TO_DB`), and separately
    crashed whenever `LOG_TO_FILE` was set (a handler was renamed without
    updating every reference to it). Sweep the flag combinations that matter
    to catch either kind of regression.
    """
    config = {
        "DEBUG": False,
        "LOG_TO_STDOUT": log_to_stdout,
        "LOG_TO_FILE": log_to_file,
        "LOG_TO_DB": log_to_db,
    }
    configure_logging(config, tmp_path)


def test_configure_logging_routes_loggers_to_base_and_access_tables(tmp_path):
    """End-to-end: with `LOG_TO_DB` on, the "access"-flavoured loggers
    (`ouranos.web_server.socketio`, `uvicorn.access`) must land in
    `AccessLog`, and everything else in `BaseLog`. This is the actual feature
    the `base_logs`/`access_logs` split exists for, so it's worth checking
    through the real `configure_logging` wiring rather than only through
    `DBHandler` directly.
    """
    config = {
        "DEBUG": False,
        "LOG_TO_STDOUT": False,
        "LOG_TO_FILE": False,
        "LOG_TO_DB": True,
    }
    configure_logging(config, tmp_path)

    base_handlers = [
        h for h in logging.getLogger("ouranos").handlers
        if isinstance(h, DBHandler)
    ]
    access_handlers = [
        h for h in logging.getLogger("ouranos.web_server.socketio").handlers
        if isinstance(h, DBHandler)
    ]
    assert len(base_handlers) == 1
    assert base_handlers[0]._table_model is BaseLog
    assert len(access_handlers) == 1
    assert access_handlers[0]._table_model is AccessLog


def test_configure_logging_debug_mode_sets_handler_levels(tmp_path):
    """Regression test: the "if config['DEBUG']" block patches every
    handler's level to DEBUG by looping over `logging_config["handlers"]` --
    but that loop runs before `LOG_TO_STDOUT`/`LOG_TO_FILE`/`LOG_TO_DB`
    populate the (now initially empty) handlers dict, so the loop always
    patches zero handlers. The logger itself does get DEBUG (that loop runs
    over the always-populated "loggers" dict), so debug records are created
    but then silently dropped by the handler's own INFO-level threshold.
    """
    config = {
        "DEBUG": True,
        "LOG_TO_STDOUT": True,
        "LOG_TO_FILE": False,
        "LOG_TO_DB": False,
    }
    configure_logging(config, tmp_path)

    logger = logging.getLogger("ouranos")
    assert logger.level == logging.DEBUG
    assert all(h.level == logging.DEBUG for h in logger.handlers)
