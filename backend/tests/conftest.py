import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"


def load_script(name: str):
    """backend/scripts is not a package; load a script as a module from its path."""
    module_name = f"scripts_{name}"
    if module_name not in sys.modules:
        spec = importlib.util.spec_from_file_location(module_name, SCRIPTS_DIR / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
    return sys.modules[module_name]


@pytest.fixture
def discovery():
    return load_script("moonraker_discovery")


@pytest.fixture
def mock_moonraker():
    """The simulated printer's app with a fresh printer, ready to be served in-process."""
    mock = load_script("mock_moonraker")
    mock.printer = mock.SimulatedPrinter(layers=4, layer_seconds=2.0, layer_height=0.2, seed=1)
    mock.auth_required_prefixes = ()
    return mock
