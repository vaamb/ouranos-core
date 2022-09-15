from __future__ import annotations

from pathlib import Path

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from .consts import ImmutableDict
from .database.wrapper import AsyncSQLAlchemyWrapper


base_dir: Path = Path(__file__).absolute().parents[1]
config: ImmutableDict[str, bool | int | str] = ImmutableDict()


db: AsyncSQLAlchemyWrapper = AsyncSQLAlchemyWrapper()
scheduler: AsyncIOScheduler = AsyncIOScheduler()


def set_base_dir(path: str | Path) -> None:
    global base_dir
    if not isinstance(path, Path):
        path = Path(path)
    if path.exists():
        base_dir = path
    else:
        path.mkdir(parents=False)
        base_dir = path


def set_config_globally(new_config: dict) -> None:
    global config
    config = ImmutableDict(new_config)
