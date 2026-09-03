"""
Dotfiles module for Clinux.
Wraps DotfilesManager for GNU Stow package link management.
"""

from typing import Any, Dict, List
from clinux.modules.base import BaseModule
from targz_manager.dotfiles_manager import DotfilesManager


class DotfilesModule(BaseModule):
    id = "dotfiles"
    name = "Dotfiles"
    description = "Dotfiles manager backed by GNU Stow and dotfiles scripts."

    def __init__(self):
        self.dm = DotfilesManager()

    def scan(self, **kwargs) -> Dict[str, Any]:
        return self.dm.get_status()

    def actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "run_command", "description": "Run dotfiles command (status, check, apply, stow, unstow, restow)"}
        ]

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        cmd = kwargs.get("command", action_name)
        pkg = kwargs.get("package")
        msg = kwargs.get("message")
        return self.dm.run_command(cmd, package=pkg, message=msg)
