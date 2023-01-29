from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ArchiveLink:
    name: str
    status: str
    _limit_key: str | None

    def __init__(self, name, status, limit_key=None) -> None:
        if status not in ("archive", "recent"):
            raise ValueError("status has to be 'archive' or 'recent'")
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "status", status)
        object.__setattr__(self, "_limit_key", limit_key)

    @property
    def limit(self) -> int | None:
        from ouranos import current_app
        if self._limit_key is not None:
            return current_app.get(self._limit_key, None)
        return None
