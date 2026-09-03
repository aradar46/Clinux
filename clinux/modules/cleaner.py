"""
Cleaner module for Clinux.
Wraps SystemCleaner and exposes standard module contract.
"""

from typing import Any, Dict, List
from clinux.modules.base import BaseModule
from targz_manager.cleaner import SystemCleaner


class CleanerModule(BaseModule):
    id = "cleaner"
    name = "Cleaner"
    description = "Purges package manager caches, dev build caches, and system junk."

    def __init__(self):
        self._cleaner = SystemCleaner()

    def scan(self, **kwargs) -> Dict[str, Any]:
        return self._cleaner.scan()

    def actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "clean", "description": "Clean specified target IDs or all safe targets"}
        ]

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        if action_name == "clean":
            target_ids = kwargs.get("target_ids")
            dry_run = kwargs.get("dry_run", False)
            if dry_run:
                scan_data = self.scan()
                return {"dry_run": True, "scan": scan_data}
            return self._cleaner.clean(target_ids)
        raise NotImplementedError(f"Action '{action_name}' is not supported.")
