from __future__ import annotations

from pathlib import Path


base_dir = Path(__file__).absolute().parents[1]
app_config: dict[str, str | int] = {}


def set_base_dir(path: str | Path):
    global base_dir
    if not isinstance(path, Path):
        path = Path(path)
    if path.exists():
        base_dir = path
    else:
        path.mkdir(parents=False)
        base_dir = path


def set_app_config(config: dict):
    global app_config
    app_config = config
