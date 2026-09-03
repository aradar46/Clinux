import os
import subprocess
from pathlib import Path
from typing import Dict, Optional, Any


class DotfilesManager:
    """
    Interfaces with ~/.dotfiles, the ~/.dotfiles/dotfiles management script,
    and GNU Stow for selective package management.
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
        "stow",
        "unstow",
        "restow",
    }

    def __init__(self, repo_dir: Optional[Path] = None, target_dir: Optional[Path] = None):
        self.repo_dir = Path(repo_dir or self.DEFAULT_REPO_DIR)
        self.target_dir = Path(target_dir or Path.home())
        self.script_path = self.repo_dir / "dotfiles"

    def is_package_stowed(self, package: str) -> bool:
        """
        Returns True if at least one file within package is currently symlinked into target_dir.
        """
        pkg_dir = self.repo_dir / package
        if not pkg_dir.is_dir():
            return False
        try:
            for root, _, files in os.walk(pkg_dir):
                for f in files:
                    rel = Path(root, f).relative_to(pkg_dir)
                    dest = self.target_dir / rel
                    if dest.is_symlink():
                        try:
                            resolved = dest.resolve()
                            if str(resolved) == str((pkg_dir / rel).resolve()):
                                return True
                        except Exception:
                            pass
        except Exception:
            pass
        return False

    def stow_package(self, package: str, action: str = "stow") -> Dict[str, Any]:
        """
        Selectively stow, unstow, or restow an individual package.
        """
        if not package or "/" in package or "\\" in package or ".." in package or package.startswith("."):
            return {
                "success": False,
                "command": f"{action} {package}",
                "output": "",
                "returncode": -1,
                "error": f"Invalid package name '{package}'. Path traversal and hidden folders not allowed.",
            }

        pkg_path = self.repo_dir / package
        if not pkg_path.exists() or not pkg_path.is_dir():
            return {
                "success": False,
                "command": f"{action} {package}",
                "output": "",
                "returncode": -1,
                "error": f"Package '{package}' not found in dotfiles repository",
            }

        # Clean accidental top-level symlink if present before linking
        if action in ("stow", "restow"):
            top_link = self.target_dir / package
            if top_link.is_symlink():
                try:
                    dest = top_link.resolve()
                    if str(dest).startswith(str(self.repo_dir.resolve())):
                        top_link.unlink()
                except Exception:
                    pass

        flag_map = {
            "stow": [],
            "unstow": ["-D"],
            "restow": ["-R"],
        }
        if action not in flag_map:
            return {
                "success": False,
                "command": f"{action} {package}",
                "output": "",
                "returncode": -1,
                "error": f"Invalid action '{action}'. Choose from: stow, unstow, restow",
            }

        cmd = ["stow", "--dir", str(self.repo_dir), "--target", str(self.target_dir), "--verbose"] + flag_map[action] + [package]
        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=60,
            )
            output = (res.stdout + res.stderr).strip()
            return {
                "success": res.returncode == 0,
                "command": f"{action} {package}",
                "output": output or f"Package '{package}' {action}ed successfully.",
                "returncode": res.returncode,
                "error": None if res.returncode == 0 else f"Stow {action} failed",
            }
        except FileNotFoundError:
            return {
                "success": False,
                "command": f"{action} {package}",
                "output": "",
                "returncode": -1,
                "error": "GNU stow binary not found. Install it via 'sudo pacman -S stow' or 'sudo apt install stow'.",
            }
        except Exception as e:
            return {
                "success": False,
                "command": f"{action} {package}",
                "output": "",
                "returncode": -1,
                "error": str(e),
            }

    def get_status(self) -> Dict[str, Any]:
        """
        Inspect git status, packages (with stowed state), and script readiness.
        """
        exists = self.repo_dir.exists() and self.repo_dir.is_dir()
        has_script = exists and self.script_path.exists() and os.access(str(self.script_path), os.X_OK)

        packages = []
        package_names = []
        if exists:
            for item in sorted(self.repo_dir.iterdir()):
                if item.is_dir() and not item.name.startswith("."):
                    stowed = self.is_package_stowed(item.name)
                    packages.append({
                        "name": item.name,
                        "stowed": stowed,
                    })
                    package_names.append(item.name)

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
            "package_names": package_names,
            "git": git_info,
        }

    def run_command(self, command: str, message: Optional[str] = None, package: Optional[str] = None) -> Dict[str, Any]:
        """
        Execute an allowed dotfiles subcommand or selective stow action safely.
        """
        if command not in self.ALLOWED_COMMANDS:
            return {
                "success": False,
                "command": command,
                "output": "",
                "returncode": -1,
                "error": f"Command '{command}' is not allowed. Allowed: {', '.join(sorted(self.ALLOWED_COMMANDS))}",
            }

        if command in ("stow", "unstow", "restow"):
            if not package:
                return {
                    "success": False,
                    "command": command,
                    "output": "",
                    "returncode": -1,
                    "error": "Package name is required for selective stow/unstow/restow",
                }
            return self.stow_package(package, action=command)

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
