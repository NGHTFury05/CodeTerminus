"""Plugin registry — discovers and loads plugins from the plugins/ directory."""
from __future__ import annotations

import importlib.util
import sys
from typing import Dict, List, Optional

from backend.config import settings
from backend.plugins.base import Plugin

_registry: Dict[str, Plugin] = {}


def load_plugins() -> List[Plugin]:
    """Scan plugins/ directory and load all valid Plugin implementations."""
    if not settings.PLUGINS_DIR.exists():
        return []

    loaded = []
    for path in sorted(settings.PLUGINS_DIR.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            spec = importlib.util.spec_from_file_location(f"ct_plugin_{path.stem}", path)
            if not (spec and spec.loader):
                continue
            module = importlib.util.module_from_spec(spec)
            sys.modules[f"ct_plugin_{path.stem}"] = module
            spec.loader.exec_module(module)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if isinstance(attr, type) and issubclass(attr, Plugin) and attr is not Plugin:
                    instance: Plugin = attr()
                    instance.on_load()
                    _registry[instance.name] = instance
                    loaded.append(instance)
                    print(f"[plugins] ✔ {instance.name} v{instance.version}")
        except Exception as e:
            print(f"[plugins] ✘ Failed to load {path.name}: {e}")

    return loaded


def get_plugins() -> List[Plugin]:
    return list(_registry.values())


def get_plugin(name: str) -> Optional[Plugin]:
    return _registry.get(name)
