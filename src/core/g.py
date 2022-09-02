from __future__ import annotations

from pathlib import Path


base_dir = Path(__file__).absolute().parents[1]


def set_base_dir(path: str | Path):
    global base_dir
    if not isinstance(path, Path):
        path = Path(path)
    if path.exists():
        base_dir = path
    else:
        path.mkdir(parents=False)
        base_dir = path
