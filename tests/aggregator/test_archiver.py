from __future__ import annotations

import logging
import types

from ouranos.aggregator.archiver import Archiver
from ouranos.core.database.models.abc import ArchivableMixin


class _FakeArchivable(ArchivableMixin):
    _archive_table = "fake_archive"
    _archive_column = "timestamp"

    @classmethod
    def get_time_limit(cls) -> int:
        return 30


def _make_module(**attrs) -> types.ModuleType:
    module = types.ModuleType("test_module")
    for name, value in attrs.items():
        setattr(module, name, value)
    return module


# ---------------------------------------------------------------------------
#   _get_archivable
# ---------------------------------------------------------------------------
def test_get_archivable_finds_subclass():
    module = _make_module(FakeModel=_FakeArchivable)
    assert Archiver._get_archivable(module) == {"fake_archive": _FakeArchivable}


def test_get_archivable_skips_non_classes():
    module = _make_module(a_string="hello", a_number=42, a_none=None, a_list=[])
    assert Archiver._get_archivable(module) == {}


def test_get_archivable_skips_mixin_itself():
    module = _make_module(ArchivableMixin=ArchivableMixin)
    assert Archiver._get_archivable(module) == {}


def test_get_archivable_skips_unrelated_classes():
    class Unrelated:
        pass

    module = _make_module(Unrelated=Unrelated)
    assert Archiver._get_archivable(module) == {}


def test_get_archivable_mixed_module():
    """Realistic case: module contains imports, constants, and models all at once."""
    class Unrelated:
        pass

    module = _make_module(
        sa="imported_module",
        a_number=42,
        Unrelated=Unrelated,
        ArchivableMixin=ArchivableMixin,
        FakeModel=_FakeArchivable,
    )
    assert Archiver._get_archivable(module) == {"fake_archive": _FakeArchivable}


# ---------------------------------------------------------------------------
#   _map_archives
# ---------------------------------------------------------------------------
def test_map_archives_warns_on_missing_archive_table(monkeypatch, caplog):
    monkeypatch.setattr("ouranos.aggregator.archiver.gaia", _make_module(FakeModel=_FakeArchivable))
    monkeypatch.setattr("ouranos.aggregator.archiver.app", _make_module())
    monkeypatch.setattr("ouranos.aggregator.archiver.archives", _make_module())

    archiver = Archiver()
    with caplog.at_level(logging.WARNING, logger="ouranos.aggregator"):
        mapping = archiver._map_archives()

    assert "fake_archive" not in mapping
    assert "fake_archive" in caplog.text
