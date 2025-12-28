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
            if f"{var_name}=" in line:
                return line.split("=")[1].strip().strip('"')
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

    def test_ouranos_version(self):
        ouranos_version = _get_var_value("OURANOS_VERSION", self.install_script_path)

        assert ouranos_version == __version__

    def test_python_version(self):
        install_version = _get_var_value("MIN_PYTHON_VERSION", self.install_script_path)

        with open(self.root_dir / "pyproject.toml", "rb") as f:
            data = tomllib.load(f)
        toml_version = data["project"]["requires-python"]
        assert toml_version[:2] == ">="
        toml_version = toml_version[2:]

        assert install_version == toml_version

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
