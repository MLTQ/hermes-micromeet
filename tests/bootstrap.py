"""Load the plugin as a package without requiring an installed copy."""

from __future__ import annotations

import importlib
import importlib.util
import os
import sys
from pathlib import Path
from types import ModuleType

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = "hermes_micromeet_under_test"


def load_module(name: str) -> ModuleType:
    _ensure_package()
    return importlib.import_module(f"{PACKAGE}.{name}")


def load_plugin() -> ModuleType:
    existing = sys.modules.get(PACKAGE)
    if existing and getattr(existing, "__file__", None):
        return existing
    source = os.getenv("HERMES_AGENT_SOURCE")
    if source and source not in sys.path:
        sys.path.insert(0, source)
    spec = importlib.util.spec_from_file_location(
        PACKAGE,
        ROOT / "__init__.py",
        submodule_search_locations=[str(ROOT)],
    )
    if spec is None or spec.loader is None:
        raise RuntimeError("could not create plugin import specification")
    module = importlib.util.module_from_spec(spec)
    sys.modules[PACKAGE] = module
    spec.loader.exec_module(module)
    return module


def _ensure_package() -> ModuleType:
    existing = sys.modules.get(PACKAGE)
    if existing:
        return existing
    package = ModuleType(PACKAGE)
    package.__path__ = [str(ROOT)]  # type: ignore[attr-defined]
    package.__package__ = PACKAGE
    sys.modules[PACKAGE] = package
    return package
