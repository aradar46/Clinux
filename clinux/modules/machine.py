"""
Machine export/restore manifest module for Clinux.
"""

from typing import Any, Dict, List, Optional
from clinux.modules.base import BaseModule
from targz_manager.db import Database
from targz_manager.machine import MachineManager


class MachineModule(BaseModule):
    id = "machine"
    name = "Machine Manifest"
    description = "Exports and restores reproducible developer machine states."

    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        self.mm = MachineManager(self.db)

    def scan(self, **kwargs) -> Dict[str, Any]:
        return {
            "status": "ready",
            "db_apps_count": len(self.db.list_apps())
        }

    def actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "export", "description": "Export machine state manifest to file"},
            {"id": "restore", "description": "Restore machine state from manifest file"}
        ]

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        if action_name == "export":
            path = kwargs.get("output_path", "clinux-machine.toml")
            out = self.mm.export_machine(path)
            return {"output_path": str(out)}
        elif action_name == "restore":
            path = kwargs.get("input_path", "clinux-machine.toml")
            res = self.mm.restore_machine(path)
            return {"results": res}

        raise NotImplementedError(f"Action '{action_name}' is not supported.")
