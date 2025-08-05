from pathlib import Path
import tomllib
from unittest import TestCase

from ouranos import __version__


def _get_var_value(var_name: str, script_path: Path) -> str:
    with open(script_path, "r") as f:
        for line in f:
            if f"{var_name}=" in line:
                return line.split("=")[1].strip().strip('"')
    raise ValueError(f"Variable {var_name} not found in {script_path}")


class TestInstallScript(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.root_dir = Path(__file__).parents[1]
        cls.scripts_dir = cls.root_dir / "scripts"
        cls.install_script_path = cls.scripts_dir / "install.sh"

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
