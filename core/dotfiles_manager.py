import os
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any, Union


class DotfilesManager:
    """
    Independent GNU Stow & Git Dotfiles Manager.
    Supports:
    - User-configured dotfiles repository path and target directory.
    - GNU Stow 80/20 operations: stow, unstow, restow, adopt, dry-run simulation, no-folding.
    - Full Git integration: status, pull, commit, push (with force flag), diff, log.
    - Multi-level package symlink & folding detection.
    """

    DEFAULT_REPO_DIR = Path.home() / ".dotfiles"
    DEFAULT_TARGET_DIR = Path.home()

    ALLOWED_STOW_ACTIONS = {"stow", "unstow", "restow"}
    ALLOWED_GIT_ACTIONS = {"pull", "commit", "push", "commit_push", "status", "diff", "log", "init"}
    ALLOWED_GIT_ACTIONS = {
        "pull",
        "rebase",
        "pull_overwrite",
        "force_pull",
        "fetch",
        "commit",
        "push",
        "commit_push",
        "status",
        "diff",
        "log",
        "init",
    }

    def __init__(
        self,
        repo_dir: Optional[Union[str, Path]] = None,
        target_dir: Optional[Union[str, Path]] = None,
        db: Optional[Any] = None,
    ):
        self.db = db
        saved_repo = None
        saved_target = None

        if self.db:
            try:
                opts = self.db.get_options().get("dotfiles", {})
                saved_repo = opts.get("repo_path")
                saved_target = opts.get("target_dir")
            except Exception:
                pass

        final_repo = repo_dir or saved_repo or self.DEFAULT_REPO_DIR
        final_target = target_dir or saved_target or self.DEFAULT_TARGET_DIR

        self.repo_dir = Path(final_repo).expanduser().resolve()
        self.target_dir = Path(final_target).expanduser().resolve()
        self.script_path = self.repo_dir / "dotfiles"

    def set_paths(
        self,
        repo_dir: Optional[Union[str, Path]] = None,
        target_dir: Optional[Union[str, Path]] = None,
        persist: bool = True,
    ) -> Dict[str, Any]:
        """
        Update dotfiles repository path and target directory, optionally persisting to database.
        """
        if repo_dir:
            self.repo_dir = Path(repo_dir).expanduser().resolve()
            self.script_path = self.repo_dir / "dotfiles"
        if target_dir:
            self.target_dir = Path(target_dir).expanduser().resolve()

        if persist and self.db:
            try:
                current_opts = self.db.get_options()
                if "dotfiles" not in current_opts:
                    current_opts["dotfiles"] = {}
                current_opts["dotfiles"]["repo_path"] = str(self.repo_dir)
                current_opts["dotfiles"]["target_dir"] = str(self.target_dir)
                self.db.save_options(current_opts)
            except Exception:
                pass

        return {
            "success": True,
            "repo_path": str(self.repo_dir),
            "target_dir": str(self.target_dir),
            "exists": self.repo_dir.exists() and self.repo_dir.is_dir(),
        }

    @staticmethod
    def is_stow_installed() -> bool:
        return shutil.which("stow") is not None

    @staticmethod
    def is_git_installed() -> bool:
        return shutil.which("git") is not None

    def validate_package_name(self, package: str) -> Optional[str]:
        """
        Validate package name to prevent path traversal and arbitrary command injections.
        """
        if not package or not isinstance(package, str):
            return "Package name is required"
        pkg = package.strip()
        if not pkg:
            return "Package name cannot be empty"
        if "/" in pkg or "\\" in pkg or ".." in pkg:
            return f"Invalid package '{pkg}': Path separators and traversal not allowed"
        if pkg.startswith("."):
            return f"Invalid package '{pkg}': Hidden directories are not stow packages"
        return None

    def get_package_names(self) -> List[str]:
        """
        Discover valid Stow packages (non-hidden subdirectories) in dotfiles repository.
        """
        if not self.repo_dir.exists() or not self.repo_dir.is_dir():
            return []

        ignored_names = {".git", ".github", ".vscode", "node_modules"}
        packages = []
        try:
            for item in sorted(self.repo_dir.iterdir()):
                if item.is_dir() and not item.name.startswith(".") and item.name not in ignored_names:
                    packages.append(item.name)
        except Exception:
            pass
        return packages

    def get_package_stow_status(self, package: str) -> Dict[str, Any]:
        """
        Inspect stow status for a package.
        Detects full stowed, partial stowed, unstowed, and folded directory symlinks.
        """
        pkg_dir = self.repo_dir / package
        if not pkg_dir.exists() or not pkg_dir.is_dir():
            return {
                "name": package,
                "status": "missing",
                "stowed": False,
                "total_files": 0,
                "stowed_files": 0,
                "files": [],
            }

        total_files = 0
        stowed_files = 0
        file_samples = []

        try:
            for root, _, files in os.walk(pkg_dir):
                for f in files:
                    total_files += 1
                    file_path = Path(root, f)
                    rel = file_path.relative_to(pkg_dir)
                    dest = self.target_dir / rel

                    is_stowed = False
                    if dest.is_symlink():
                        try:
                            if dest.resolve() == file_path.resolve():
                                is_stowed = True
                        except Exception:
                            pass

                    if not is_stowed:
                        curr = dest.parent
                        while curr != self.target_dir and curr != curr.parent:
                            if curr.is_symlink():
                                try:
                                    rel_parent = curr.relative_to(self.target_dir)
                                    src_parent = pkg_dir / rel_parent
                                    if curr.resolve() == src_parent.resolve():
                                        is_stowed = True
                                        break
                                except Exception:
                                    pass
                            curr = curr.parent

                    if is_stowed:
                        stowed_files += 1

                    if len(file_samples) < 25:
                        file_samples.append({
                            "path": str(rel),
                            "stowed": is_stowed,
                        })
        except Exception:
            pass

        if total_files == 0:
            status = "empty"
            stowed = False
        elif stowed_files == total_files:
            status = "stowed"
            stowed = True
        elif stowed_files > 0:
            status = "partial"
            stowed = False
        else:
            status = "unstowed"
            stowed = False

        return {
            "name": package,
            "status": status,
            "stowed": stowed,
            "total_files": total_files,
            "stowed_files": stowed_files,
            "files": file_samples,
        }

    def is_package_stowed(self, package: str) -> bool:
        """
        Legacy helper: returns True if at least one file is stowed.
        """
        status = self.get_package_stow_status(package)
        return status["stowed_files"] > 0

    def get_git_info(self) -> Dict[str, Any]:
        """
        Get comprehensive Git status for the dotfiles repository.
        """
        git_info = {
            "is_git": False,
            "branch": "",
            "clean": True,
            "modified_files": 0,
            "untracked_files": 0,
            "ahead": 0,
            "behind": 0,
            "remote": "",
            "last_commit": "",
            "status_summary": "",
        }

        if not self.repo_dir.exists() or not (self.repo_dir / ".git").exists():
            return git_info

        if not self.is_git_installed():
            git_info["is_git"] = True
            git_info["status_summary"] = "Git binary not found on system."
            return git_info

        git_info["is_git"] = True
        try:
            res_b = subprocess.run(
                ["git", "status", "--porcelain=v1", "-b"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=8,
            )
            if res_b.returncode == 0:
                lines = [ln.strip() for ln in res_b.stdout.splitlines() if ln.strip()]
                if lines:
                    header = lines[0]
                    if header.startswith("## "):
                        branch_part = header[3:]
                        if "..." in branch_part:
                            local_b = branch_part.split("...")[0]
                            git_info["branch"] = local_b
                            if "[" in branch_part and "]" in branch_part:
                                track_info = branch_part[branch_part.find("[") + 1 : branch_part.find("]")]
                                if "ahead" in track_info:
                                    try:
                                        git_info["ahead"] = int(track_info.split("ahead")[1].split(",")[0].strip())
                                    except Exception:
                                        pass
                                if "behind" in track_info:
                                    try:
                                        git_info["behind"] = int(track_info.split("behind")[1].split(",")[0].strip())
                                    except Exception:
                                        pass
                        else:
                            git_info["branch"] = branch_part.split()[0]
                    else:
                        git_info["branch"] = header

                    changes = lines[1:]
                    git_info["clean"] = len(changes) == 0
                    git_info["modified_files"] = sum(1 for ln in changes if not ln.startswith("??"))
                    git_info["untracked_files"] = sum(1 for ln in changes if ln.startswith("??"))
                    git_info["status_summary"] = "\n".join(changes[:30])

            res_r = subprocess.run(
                ["git", "config", "--get", "remote.origin.url"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res_r.returncode == 0:
                git_info["remote"] = res_r.stdout.strip()

            res_l = subprocess.run(
                ["git", "log", "-1", "--pretty=format:%h - %s (%cr)"],
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res_l.returncode == 0:
                git_info["last_commit"] = res_l.stdout.strip()

        except Exception as e:
            git_info["status_summary"] = f"Error inspecting git status: {e}"

        return git_info

    def get_status(self) -> Dict[str, Any]:
        """
        Inspect dotfiles repository readiness, packages, and Git state.
        """
        exists = self.repo_dir.exists() and self.repo_dir.is_dir()
        has_script = exists and self.script_path.exists() and os.access(str(self.script_path), os.X_OK)

        packages = []
        package_names = []

        if exists:
            raw_packages = self.get_package_names()
            for pkg in raw_packages:
                pkg_info = self.get_package_stow_status(pkg)
                packages.append(pkg_info)
                package_names.append(pkg)

        return {
            "exists": exists,
            "has_script": has_script,
            "repo_path": str(self.repo_dir),
            "target_dir": str(self.target_dir),
            "stow_installed": self.is_stow_installed(),
            "git_installed": self.is_git_installed(),
            "packages": packages,
            "package_names": package_names,
            "git": self.get_git_info(),
        }

    def run_stow(
        self,
        action: str = "stow",
        package: Optional[str] = None,
        simulate: bool = False,
        adopt: bool = False,
        no_folding: bool = False,
        override: Optional[str] = None,
        dotfiles_flag: bool = False,
        target_dir: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute GNU Stow operations with 80/20 flags.
        Supports single package or batch all packages.
        """
        if not self.is_stow_installed():
            return {
                "success": False,
                "command": "stow",
                "output": "",
                "returncode": -1,
                "error": "GNU Stow binary not found. Install it via 'sudo pacman -S stow' or distro package manager.",
            }

        if not self.repo_dir.exists() or not self.repo_dir.is_dir():
            return {
                "success": False,
                "command": "stow",
                "output": "",
                "returncode": -1,
                "error": f"Dotfiles directory not found at {self.repo_dir}",
            }

        if action not in self.ALLOWED_STOW_ACTIONS:
            return {
                "success": False,
                "command": action,
                "output": "",
                "returncode": -1,
                "error": f"Invalid stow action '{action}'. Choose from: {', '.join(sorted(self.ALLOWED_STOW_ACTIONS))}",
            }

        target = Path(target_dir).expanduser().resolve() if target_dir else self.target_dir

        targets = []
        if package and package != "__all__":
            err = self.validate_package_name(package)
            if err:
                return {
                    "success": False,
                    "command": f"{action} {package}",
                    "output": "",
                    "returncode": -1,
                    "error": err,
                }
            pkg_path = self.repo_dir / package
            if not pkg_path.exists() or not pkg_path.is_dir():
                return {
                    "success": False,
                    "command": f"{action} {package}",
                    "output": "",
                    "returncode": -1,
                    "error": f"Package '{package}' not found in {self.repo_dir}",
                }
            targets = [package]
        else:
            targets = self.get_package_names()
            if not targets:
                return {
                    "success": False,
                    "command": action,
                    "output": "",
                    "returncode": -1,
                    "error": "No stow packages found in dotfiles directory",
                }

        cmd = ["stow", "-v"]

        if simulate:
            cmd.append("-n")
        if adopt:
            cmd.append("--adopt")
        if no_folding:
            cmd.append("--no-folding")
        if dotfiles_flag:
            cmd.append("--dotfiles")
        if override:
            cmd.extend(["--override", override])

        cmd.extend(["-d", str(self.repo_dir), "-t", str(target)])

        if action == "unstow":
            cmd.append("-D")
        elif action == "restow":
            cmd.append("-R")
        elif action == "stow":
            cmd.append("-S")

        cmd.extend(targets)

        try:
            res = subprocess.run(
                cmd,
                cwd=str(self.repo_dir),
                capture_output=True,
                text=True,
                timeout=120,
            )
            raw_out = (res.stdout + "\n" + res.stderr).strip()
            summary = raw_out or f"Stow {action} completed successfully for {', '.join(targets)}."
            summary = raw_out or f"{action.capitalize()} completed successfully for {', '.join(targets)}."

            return {
                "success": res.returncode == 0,
                "action": action,
                "command": " ".join(cmd),
                "output": summary,
                "returncode": res.returncode,
                "error": None if res.returncode == 0 else f"Stow {action} failed (code {res.returncode})",
            }
        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "action": action,
                "command": " ".join(cmd),
                "output": "Operation timed out after 120 seconds",
                "returncode": -1,
                "error": "Timeout expired",
            }
        except Exception as e:
            return {
                "success": False,
                "action": action,
                "command": " ".join(cmd),
                "output": "",
                "returncode": -1,
                "error": str(e),
            }

    def stow_package(self, package: str, action: str = "stow") -> Dict[str, Any]:
        return self.run_stow(action=action, package=package)

    def run_git(
        self,
        action: str,
        message: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Execute Git operations on the dotfiles repository.
        Supports: status, diff, log, pull, commit, push (with force flag), commit_push.
        """
        if not self.is_git_installed():
            return {
                "success": False,
                "action": action,
                "command": "git",
                "output": "",
                "returncode": -1,
                "error": "Git binary not found on system.",
            }

        if not self.repo_dir.exists() or not self.repo_dir.is_dir():
            return {
                "success": False,
                "action": action,
                "command": "git",
                "output": "",
                "returncode": -1,
                "error": f"Repository directory not found at {self.repo_dir}",
            }

        if action not in self.ALLOWED_GIT_ACTIONS:
            return {
                "success": False,
                "action": action,
                "command": "git",
                "output": "",
                "returncode": -1,
                "error": f"Invalid git action '{action}'. Allowed: {', '.join(sorted(self.ALLOWED_GIT_ACTIONS))}",
            }

        is_git = (self.repo_dir / ".git").exists()
        if action != "init" and not is_git:
            return {
                "success": False,
                "action": action,
                "command": f"git {action}",
                "output": "",
                "returncode": -1,
                "error": f"Directory {self.repo_dir} is not a git repository.",
            }

        try:
            if action == "init":
                cmd = ["git", "init"]
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=15)
                return {
                    "success": res.returncode == 0,
                    "action": action,
                    "command": "git init",
                    "output": (res.stdout + res.stderr).strip(),
                    "returncode": res.returncode,
                    "error": None if res.returncode == 0 else "Failed to initialize git repository",
                }

            elif action == "status":
                cmd = ["git", "status", "-s"]
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=10)
                out = (res.stdout + res.stderr).strip() or "Working tree clean."
                return {
                    "success": res.returncode == 0,
                    "action": action,
                    "command": "git status -s",
                    "output": out,
                    "returncode": res.returncode,
                    "error": None,
                }

            elif action == "diff":
                cmd = ["git", "diff", "HEAD"]
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=15)
                out = (res.stdout + res.stderr).strip() or "No uncommitted diff."
                return {
                    "success": res.returncode == 0,
                    "action": action,
                    "command": "git diff HEAD",
                    "output": out,
                    "returncode": res.returncode,
                    "error": None,
                }

            elif action == "log":
                cmd = ["git", "log", "-10", "--oneline"]
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=10)
                return {
                    "success": res.returncode == 0,
                    "action": action,
                    "command": "git log -10 --oneline",
                    "output": (res.stdout + res.stderr).strip(),
                    "returncode": res.returncode,
                    "error": None,
                }

            elif action == "pull":
                cmd = ["git", "pull"]
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60)
                out = (res.stdout + res.stderr).strip()
                return {
                    "success": res.returncode == 0,
                    "action": action,
                    "command": "git pull",
                    "output": out,
                    "returncode": res.returncode,
                    "error": None if res.returncode == 0 else "Git pull failed",
                }

            elif action == "rebase":
                cmd = ["git", "pull", "--rebase"]
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60)
                out = (res.stdout + res.stderr).strip()
                return {
                    "success": res.returncode == 0,
                    "action": action,
                    "command": "git pull --rebase",
                    "output": out,
                    "returncode": res.returncode,
                    "error": None if res.returncode == 0 else "Git rebase pull failed",
                }

            elif action in ("pull_overwrite", "force_pull"):
                fetch_res = subprocess.run(["git", "fetch", "--all"], cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60)
                if fetch_res.returncode != 0:
                    return {
                        "success": False,
                        "action": action,
                        "command": "git fetch --all",
                        "output": (fetch_res.stdout + "\n" + fetch_res.stderr).strip(),
                        "returncode": fetch_res.returncode,
                        "error": "Git fetch failed",
                    }

                # Resolve upstream branch target
                target_ref = "@{u}"
                chk_u = subprocess.run(["git", "rev-parse", "--abbrev-ref", "@{u}"], cwd=str(self.repo_dir), capture_output=True, text=True, timeout=5)
                if chk_u.returncode != 0:
                    git_info = self.get_git_info()
                    branch = git_info.get("branch") or "main"
                    target_ref = f"origin/{branch}"

                r_res = subprocess.run(["git", "reset", "--hard", target_ref], cwd=str(self.repo_dir), capture_output=True, text=True, timeout=30)
                c_res = subprocess.run(["git", "clean", "-fd"], cwd=str(self.repo_dir), capture_output=True, text=True, timeout=30)

                combined = [
                    f"--> git fetch --all:\n{(fetch_res.stdout + fetch_res.stderr).strip() or 'OK'}",
                    f"--> git reset --hard {target_ref}:\n{(r_res.stdout + r_res.stderr).strip() or 'OK'}",
                ]
                if c_res.stdout or c_res.stderr:
                    combined.append(f"--> git clean -fd:\n{(c_res.stdout + c_res.stderr).strip()}")

                return {
                    "success": r_res.returncode == 0,
                    "action": action,
                    "command": f"git fetch --all && git reset --hard {target_ref} && git clean -fd",
                    "output": "\n\n".join(combined),
                    "returncode": r_res.returncode,
                    "error": None if r_res.returncode == 0 else f"Reset to {target_ref} failed",
                }

            elif action == "fetch":
                cmd = ["git", "fetch", "--all"]
                res = subprocess.run(cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60)
                out = (res.stdout + "\n" + res.stderr).strip() or "Fetch completed."
                return {
                    "success": res.returncode == 0,
                    "action": action,
                    "command": "git fetch --all",
                    "output": out,
                    "returncode": res.returncode,
                    "error": None if res.returncode == 0 else "Git fetch failed",
                }

            elif action == "commit":
                msg = (message or "Update dotfiles").strip()
                add_res = subprocess.run(["git", "add", "-A"], cwd=str(self.repo_dir), capture_output=True, text=True, timeout=20)
                if add_res.returncode != 0:
                    return {
                        "success": False,
                        "action": action,
                        "command": "git add -A",
                        "output": (add_res.stdout + add_res.stderr).strip(),
                        "returncode": add_res.returncode,
                        "error": "Failed to stage changes",
                    }
                commit_cmd = ["git", "commit", "-m", msg]
                c_res = subprocess.run(commit_cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=20)
                out = (c_res.stdout + c_res.stderr).strip()
                return {
                    "success": c_res.returncode == 0,
                    "action": action,
                    "command": f'git commit -m "{msg}"',
                    "output": out,
                    "returncode": c_res.returncode,
                    "error": None if c_res.returncode == 0 else "Commit failed (maybe nothing to commit)",
                }

            elif action == "push":
                push_cmd = ["git", "push"]
                if force:
                    push_cmd.append("--force-with-lease")
                p_res = subprocess.run(push_cmd, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=60)
                out = (p_res.stdout + p_res.stderr).strip()
                return {
                    "success": p_res.returncode == 0,
                    "action": action,
                    "command": " ".join(push_cmd),
                    "output": out or ("Pushed successfully." if p_res.returncode == 0 else "Push failed."),
                    "returncode": p_res.returncode,
                    "error": None if p_res.returncode == 0 else "Git push failed",
                }

            elif action == "commit_push":
                msg = (message or "Update dotfiles").strip()
                c_res = self.run_git("commit", message=msg)
                combined_output = [f"--> git commit:\n{c_res.get('output', '')}"]
                if not c_res["success"] and "nothing to commit" not in c_res.get("output", "").lower():
                    return {
                        "success": False,
                        "action": action,
                        "command": "commit_push",
                        "output": "\n\n".join(combined_output),
                        "returncode": c_res.get("returncode", -1),
                        "error": c_res.get("error"),
                    }

                p_res = self.run_git("push", force=force)
                combined_output.append(f"--> git push:\n{p_res.get('output', '')}")
                return {
                    "success": p_res["success"],
                    "action": action,
                    "command": f"commit & {p_res.get('command')}",
                    "output": "\n\n".join(combined_output),
                    "returncode": p_res.get("returncode", 0),
                    "error": p_res.get("error"),
                }

        except subprocess.TimeoutExpired:
            return {
                "success": False,
                "action": action,
                "command": f"git {action}",
                "output": "Git operation timed out",
                "returncode": -1,
                "error": "Timeout expired",
            }
        except Exception as e:
            return {
                "success": False,
                "action": action,
                "command": f"git {action}",
                "output": "",
                "returncode": -1,
                "error": str(e),
            }

    def run_command(
        self,
        command: str,
        message: Optional[str] = None,
        package: Optional[str] = None,
        force: bool = False,
    ) -> Dict[str, Any]:
        """
        Unified command dispatcher.
        Maintains backward compatibility with legacy custom scripts while routing
        first-class stow and git commands.
        """
        if self.script_path.exists() and os.access(str(self.script_path), os.X_OK):
            cmd_args = [str(self.script_path), command]
            if message:
                cmd_args.append(message)
            try:
                res = subprocess.run(cmd_args, cwd=str(self.repo_dir), capture_output=True, text=True, timeout=120)
                if res.returncode == 0:
                    return {
                        "success": True,
                        "command": command,
                        "output": (res.stdout + res.stderr).strip(),
                        "returncode": res.returncode,
                        "error": None,
                    }
            except Exception:
                pass

        if command in self.ALLOWED_STOW_ACTIONS:
            if not package:
                return {
                    "success": False,
                    "command": command,
                    "output": "",
                    "returncode": -1,
                    "error": "Package name is required for selective stow/unstow/restow",
                }
            return self.run_stow(action=command, package=package)

        if command in self.ALLOWED_GIT_ACTIONS or command in ("save", "update"):
            if command == "save":
                return self.run_git("commit_push", message=message, force=force)
            if command == "update":
                return self.run_git("pull")
            return self.run_git(command, message=message, force=force)

        if command == "check":
            return self.run_stow(action="stow", package=package, simulate=True)
        if command == "apply":
            return self.run_stow(action="stow", package=package)

        return {
            "success": False,
            "command": command,
            "output": "",
            "returncode": -1,
            "error": f"Command '{command}' is not allowed.",
        }
