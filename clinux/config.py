"""
Declarative configuration manager for Clinux.
Uses standard JSON file format for Python 3.8+ compatibility.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional
from clinux.paths import DEFAULT_CONFIG_PATH, CLINUX_CONFIG_DIR


DEFAULT_CONFIG: Dict[str, Any] = {
    "version": 1,
    "general": {
        "auto_open_browser": True,
        "default_port": 8421,
        "dry_run": False,
        "verbose": False
    },
    "modules": {
        "cleaner": {"enabled": True},
        "apps": {"enabled": True},
        "skills": {"enabled": True},
        "dotfiles": {"enabled": True},
        "security": {"enabled": True},
        "machine": {"enabled": True},
        "storage": {"enabled": True}
    }
}


class Config:
    def __init__(self, config_path: Optional[Path] = None):
        self.config_path = config_path or DEFAULT_CONFIG_PATH
        self._data: Dict[str, Any] = {}
        self.load()

    def load(self) -> None:
        if self.config_path.exists():
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    self._data = json.load(f)
            except Exception:
                self._data = json.loads(json.dumps(DEFAULT_CONFIG))
        else:
            self._data = json.loads(json.dumps(DEFAULT_CONFIG))

    def save(self) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self._data, f, indent=2)

    def get(self, key_path: str, default: Any = None) -> Any:
        keys = key_path.split(".")
        curr = self._data
        for k in keys:
            if isinstance(curr, dict) and k in curr:
                curr = curr[k]
            else:
                return default
        return curr

    def set(self, key_path: str, value: Any) -> None:
        keys = key_path.split(".")
        curr = self._data
        for k in keys[:-1]:
            if k not in curr or not isinstance(curr[k], dict):
                curr[k] = {}
            curr = curr[k]
        curr[keys[-1]] = value
        self.save()

    def to_dict(self) -> Dict[str, Any]:
        return json.loads(json.dumps(self._data))
