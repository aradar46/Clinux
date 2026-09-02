import os
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any


class DotfilesManager:
    """
    Interfaces with ~/.dotfiles and the ~/.dotfiles/dotfiles management script.
    """

    DEFAULT_REPO_DIR = Path.home() / ".dotfiles"
    ALLOWED_COMMANDS = {
        "check",
        "apply",
        "update",
        "save",
        "status",
        "gnome-out",
        "gnome-in",
    }

    def __init__(self, repo_dir: Optional[Path] = None):
        self.repo_dir = Path(repo_dir or self.DEFAULT_REPO_DIR)
        self.script_path = self.repo_dir / "dotfiles"

    def get_status(self) -> Dict[str, Any]:
        """
        Inspect git status, packages, and script readiness in the dotfiles repo.
        """
        exists = self.repo_dir.exists() and self.repo_dir.is_dir()
        has_script = exists and self.script_path.exists() and os.access(str(self.script_path), os.X_OK)

        packages = []
        if exists:
            for item in sorted(self.repo_dir.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    packages.append(item.name)

        git_info = {
            "is_git": False,
            "branch": "",
            "clean": True,
            "modified_files": 0,
            "last_commit": "",
        }

        if exists and (self.repo_dir / ".git").exists():
            git_info["is_git"] = True
            try:
                # Get current branch
                res_branch = subprocess.run(
                    ["git", "rev-parse", "--abbrev-ref", "HEAD"],
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res_branch.returncode == 0:
                    git_info["branch"] = res_branch.stdout.strip()

                # Get status porcelain
                res_status = subprocess.run(
                    ["git", "status", "--porcelain"],
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res_status.returncode == 0:
                    lines = [ln for ln in res_status.stdout.splitlines() if ln.strip()]
                    git_info["modified_files"] = len(lines)
                    git_info["clean"] = len(lines) == 0

                # Get last commit
                res_log = subprocess.run(
                    ["git", "log", "-1", "--pretty=format:%h - %s (%cr)"],
                    cwd=str(self.repo_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res_log.returncode == 0:
                    git_info["last_commit"] = res_log.stdout.strip()
            except Exception:
                pass

        return {
            "exists": exists,
            "has_script": has_script,
            "repo_path": str(self.repo_dir),
            "script_path": str(self.script_path),
            "packages": packages,
            "git": git_info,
        }

    def run_command(self, command: str, message: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute an allowed dotfiles subcommand safely.
        """
        if command not in self.ALLOWED_COMMANDS:
            return {
                "success": False,
                "command": command,
                "output": "",
                "returncode": -1,
                "error": f"Command '{command}' is not allowed. Allowed: {', '.join(sorted(self.ALLOWED_COMMANDS))}",
            }

        if not self.script_path.exists():
            return {
                "success": False,
                "command": command,
                "output": "",
                "returncode": -1,
                "error": f"Dotfiles script not found at {self.script_path}",
            }

        cmd_args = [str(self.script_path), command]
        if command == "save":
            msg = (message or "Update dotfiles").strip()
            cmd_args.append(msg)

        try:
            res = subprocess.run(
                cmd_args,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            output = (res.stdout + res.stderr).strip()
            return {
                "success": res.returncode == 0,
                "command": command,
                "output": output,
                "returncode": res.returncode,
                "error": None if res.returncode == 0 else "Command exited with error",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "command": command,
                "output": "Command timed out after 120 seconds",
                "returncode": -1,
                "error": "Timeout expired",
            }
        except Exception as e:
            return {
                "success": False,
                "command": command,
                "output": "",
                "returncode": -1,
                "error": str(e),
            }

