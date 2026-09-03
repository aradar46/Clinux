"""
Security module for Clinux (System Doctor).
Diagnoses broken systemd services, old kernels, filesystem issues, and desktop shortcuts.
"""

from typing import Any, Dict, List
from clinux.modules.base import BaseModule
from targz_manager.cleaner import SystemCleaner
from targz_manager.doctor import SystemDoctor


class SecurityModule(BaseModule):
    id = "security"
    name = "Security & Health"
    description = "System Doctor audit: checks services, kernels, desktop shortcuts, and system health."

    def __init__(self):
        self.cleaner = SystemCleaner()
        self.doctor = SystemDoctor(cleaner=self.cleaner)

    def scan(self, **kwargs) -> Dict[str, Any]:
        return self.doctor.scan()

    def actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "fix", "description": "Auto-fix fixable security and system problems"}
        ]

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        if action_name == "fix":
            scan_res = self.scan()
            problems = scan_res.get("all_problems", [])
            fixed_count = 0
            results = []
            for p in problems:
                if p.get("fixable"):
                    success = self.doctor.fix(p)
                    if success:
                        fixed_count += 1
                    results.append({"problem": p["description"], "fixed": success})
            return {"fixed_count": fixed_count, "results": results}

        raise NotImplementedError(f"Action '{action_name}' is not supported.")
