"""
Storage module for Clinux.
Manages AI weights, agent workspaces, and disk usage analysis.
"""

from typing import Any, Dict, List
from clinux.modules.base import BaseModule
from targz_manager.cleaner import SystemCleaner
from targz_manager.ai_manager import AIStorageManager
from targz_manager.disk_analyzer import DiskAnalyzer


class StorageModule(BaseModule):
    id = "storage"
    name = "Storage & AI Weights"
    description = "Analyzes storage usage and manages local AI model weights / workspaces."

    def __init__(self):
        self.ai_storage = AIStorageManager()
        self.cleaner = SystemCleaner()
        self.disk_analyzer = DiskAnalyzer(ai_storage=self.ai_storage, cleaner=self.cleaner)

    def scan(self, **kwargs) -> Dict[str, Any]:
        disk_data = self.disk_analyzer.analyze()
        ai_data = self.ai_storage.scan_all()
        return {
            "disk": disk_data,
            "ai_storage": ai_data
        }

    def actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "delete_model", "description": "Delete AI model weight directory"},
            {"id": "clean_workspace", "description": "Clean AI agent workspace"}
        ]

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        if action_name == "delete_model":
            model_id = kwargs.get("model_id")
            return self.ai_storage.delete_model(model_id)
        elif action_name == "clean_workspace":
            workspace_id = kwargs.get("workspace_id")
            return self.ai_storage.clean_workspace(workspace_id)

        raise NotImplementedError(f"Action '{action_name}' is not supported.")
