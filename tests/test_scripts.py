from __future__ import annotations

from pathlib import Path
import typing as t
from unittest import TestCase

from ouranos import __version__

if t.TYPE_CHECKING:
    import re


def _get_var_value(var_name: str, script_path: Path) -> str:
    with open(script_path, "r") as f:
        for line in f:
            if f"{var_name}=" in line or f"{var_name} = " in line:
                return line.split("=", 1)[1].strip().strip('"')
    raise ValueError(f"Variable {var_name} not found in {script_path}")


def _get_pattern(script_path: Path, pattern: re.Pattern) -> str:
    with open(script_path, "r") as f:
        script_text = f.read()

    search = pattern.search(script_text)
    if search is not None:
        return search.group(0)
    raise ValueError(f"Pattern {pattern} not found in {script_path}")


class TestInstallScript(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).parents[1]
        cls.scripts_dir = cls.root_dir / "scripts"
        cls.install_script_path = cls.scripts_dir / "install.sh"
        cls.update_script_path = cls.scripts_dir / "update_ouranos.sh"
        cls.logging_script_path = cls.scripts_dir / "utils" / "logging.sh"
        cls.master_pyproject_path = cls.scripts_dir / "utils" / "gen_pyproject.sh"

    def test_ouranos_version(self):
        # Sync the version between ouranos-core and install.sh
        install_version = _get_var_value("OURANOS_VERSION", self.install_script_path)

        assert install_version == __version__

        # Sync the version between ouranos-core and gen_pyproject.sh
        master_version = _get_var_value("version", self.master_pyproject_path)

        assert master_version == __version__


    def test_python_version(self):
        # Get the core pyproject version
        core_pyproject_path = self.root_dir / "pyproject.toml"
        core_version = _get_var_value("requires-python",core_pyproject_path)
        assert core_version[:2] == ">="
        core_version = core_version[2:]

        # Get the master pyproject version
        ouranos_version = _get_var_value("requires-python", self.master_pyproject_path)
        assert ouranos_version[:2] == ">="
        ouranos_version = ouranos_version[2:]

        # Ensure both versions are identical
        assert ouranos_version == core_version

        # Get the installed version
        installed_version = _get_var_value("PYTHON_VERSION", self.install_script_path)

        # Ensure the installed version is higher than the minimum version
        installed_version_tpl = tuple(int(x) for x in installed_version.split("."))
        core_version_tpl = tuple(int(x) for x in core_version.split("."))
        assert installed_version_tpl >= core_version_tpl

    def test_logging_sync(self):
        import re

        pattern = re.compile(r"#>>>Logging>>>.*#<<<Logging<<<", re.DOTALL)

        install_code = _get_pattern(self.install_script_path, pattern)
        logging_code = _get_pattern(self.logging_script_path, pattern)

        assert install_code == logging_code

    def test_copy_sync(self):
        import re

        pattern = re.compile(r"#>>>Copy>>>.*#<<<Copy<<<", re.DOTALL)

        install_code = _get_pattern(self.install_script_path, pattern)
        update_code = _get_pattern(self.update_script_path, pattern)

        assert install_code == update_code
