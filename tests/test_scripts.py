from __future__ import annotations

from pathlib import Path
import tomllib
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
        # Sync the version between ouranos-core and install.sh
        with open(self.root_dir / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        core_version = data["project"]["requires-python"]
        assert core_version[:2] == ">="
        core_version = core_version[2:]

        install_version = _get_var_value("MIN_PYTHON_VERSION", self.install_script_path)

        assert install_version == core_version

        # Sync the version between ouranos-core and gen_pyproject.sh
        ouranos_version = _get_var_value("requires-python", self.master_pyproject_path)
        assert ouranos_version[:2] == ">="
        ouranos_version = ouranos_version[2:]

        assert ouranos_version == core_version

    def test_logging_sync(self):
        import re

        pattern = re.compile(r"#>>>Logging>>>.*#<<<Logging<<<", re.DOTALL)

        install_code = _get_pattern(self.install_script_path, pattern)
        install_code = install_code.replace("LOG_FILE", "LOGGING_FILE")
        logging_code = _get_pattern(self.logging_script_path, pattern)

        assert install_code == logging_code

    def test_copy_sync(self):
        import re

        pattern = re.compile(r"#>>>Copy>>>.*#<<<Copy<<<", re.DOTALL)

        install_code = _get_pattern(self.install_script_path, pattern)
        update_code = _get_pattern(self.update_script_path, pattern)

        assert install_code == update_code
