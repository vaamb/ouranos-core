from pathlib import Path

import pytest
from sqlalchemy import text

from sqlalchemy_wrapper import AsyncSQLAlchemyWrapper

from ouranos.core.database.init import check_db_revision


def _get_db(db_path: Path) -> AsyncSQLAlchemyWrapper:
    db = AsyncSQLAlchemyWrapper()
    db.init({
        "SQLALCHEMY_DATABASE_URI": f"sqlite+aiosqlite:///{db_path}",
        "SQLALCHEMY_BINDS": {},
    })
    return db


@pytest.mark.asyncio
class TestCheckDbRevision:
    async def test_check_db_revision_failure_missing_db(self, tmp_path: Path):
        db = _get_db(tmp_path / "missing_dir" / "ecosystems.db")

        with pytest.raises(Exception, match="no revision .* ecosystem.* fill-db"):
            await check_db_revision(db)

        for engine in db.engines.values():
            await engine.dispose()

    async def test_check_db_revision_failure_not_stamped(self, tmp_path: Path):
        db = _get_db(tmp_path / "ecosystems.db")
        async with db.get_engine_for_bind(None).begin() as connection:
            await connection.execute(text("CREATE TABLE dummy (id INTEGER)"))

        with pytest.raises(Exception, match="no revision .* ecosystem.* fill-db"):
            await check_db_revision(db)

        for engine in db.engines.values():
            await engine.dispose()

    async def test_check_db_revision_failure_outdated(self, tmp_path: Path):
        db = _get_db(tmp_path / "ecosystems.db")
        async with db.get_engine_for_bind(None).begin() as connection:
            await connection.execute(
                text("CREATE TABLE alembic_version (version_num VARCHAR(32))"))
            await connection.execute(
                text("INSERT INTO alembic_version VALUES ('outdated')"))

        with pytest.raises(Exception, match="not up to date .* ecosystem"):
            await check_db_revision(db)

        for engine in db.engines.values():
            await engine.dispose()
