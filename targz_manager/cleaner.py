import os
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Any

from .db import Database
from .installer import Installer


class SystemCleaner:
    """
    Scanner and cleaner for package manager caches, developer runtimes,
    and desktop temporary files.
    """

    DEFAULT_TARGETS = [
        # Package Managers
        {
            "id": "pacman",
            "name": "Pacman Package Cache",
            "category": "package_managers",
            "path": Path("/var/cache/pacman/pkg"),
            "description": "Arch Linux downloaded package archives (.pkg.tar.zst).",
            "safe_to_clean": True,
            "needs_sudo": True,
            "sudo_command": "sudo pacman -Scc",
            "default_checked": False,
        },
        {
            "id": "yay",
            "name": "Yay AUR Cache",
            "category": "package_managers",
            "path": Path.home() / ".cache" / "yay",
            "description": "Yay AUR helper package clones, git sources, and built packages.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "paru",
            "name": "Paru AUR Cache",
            "category": "package_managers",
            "path": Path.home() / ".cache" / "paru",
            "description": "Paru AUR helper package clones and build artifacts.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "flatpak_tmp",
            "name": "Flatpak Temp Repo Cache",
            "category": "package_managers",
            "path": Path.home() / ".local" / "share" / "flatpak" / "repo" / "tmp",
            "description": "Flatpak temporary download and repository cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "apt",
            "name": "APT Package Cache",
            "category": "package_managers",
            "path": Path("/var/cache/apt/archives"),
            "description": "Debian/Ubuntu downloaded .deb package archives.",
            "safe_to_clean": True,
            "needs_sudo": True,
            "sudo_command": "sudo apt-get clean",
            "default_checked": False,
        },
        {
            "id": "dnf",
            "name": "DNF Package Cache",
            "category": "package_managers",
            "path": Path("/var/cache/dnf"),
            "description": "Fedora/RHEL downloaded RPM package metadata and cache.",
            "safe_to_clean": True,
            "needs_sudo": True,
            "sudo_command": "sudo dnf clean all",
            "default_checked": False,
        },
        {
            "id": "miniforge_pkgs",
            "name": "Miniforge Package Tarballs",
            "category": "package_managers",
            "path": Path.home() / "miniforge3" / "pkgs",
            "description": "Downloaded conda package archives (.conda, .tar.bz2). Safe to remove.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "miniconda_pkgs",
            "name": "Miniconda Package Tarballs",
            "category": "package_managers",
            "path": Path.home() / "miniconda3" / "pkgs",
            "description": "Downloaded conda package archives (.conda, .tar.bz2). Safe to remove.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "conda_pkgs",
            "name": "Conda Package Tarballs",
            "category": "package_managers",
            "path": Path.home() / ".conda" / "pkgs",
            "description": "Downloaded conda package archives (.conda, .tar.bz2). Safe to remove.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "micromamba_pkgs",
            "name": "Micromamba Package Tarballs",
            "category": "package_managers",
            "path": Path.home() / ".micromamba" / "pkgs",
            "description": "Downloaded micromamba package archives (.conda, .tar.bz2). Safe to remove.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "snap_cache",
            "name": "Snap Package Cache",
            "category": "package_managers",
            "path": Path("/var/lib/snapd/cache"),
            "description": "Snap downloaded package cache on Ubuntu/Debian.",
            "safe_to_clean": True,
            "needs_sudo": True,
            "sudo_command": "sudo rm -rf /var/lib/snapd/cache/*",
            "default_checked": True,
        },

        # Developer Tools & Runtimes
        {
            "id": "pip",
            "name": "Pip Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "pip",
            "description": "Python pip downloaded wheels, packages, and HTTP response cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "uv_cache",
            "name": "uv Python Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "uv",
            "description": "uv Python package manager wheel and source archive cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "poetry_cache",
            "name": "Poetry Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "pypoetry",
            "description": "Poetry Python dependency manager wheel and repository cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "npm",
            "name": "Npm Cache",
            "category": "developer",
            "path": Path.home() / ".npm" / "_cacache",
            "description": "Node.js npm package download and integrity cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "yarn",
            "name": "Yarn Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "yarn",
            "description": "Yarn package manager downloaded tarball cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "pnpm",
            "name": "Pnpm Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "pnpm",
            "description": "Pnpm package metadata and download cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "cargo_cache",
            "name": "Cargo Crates Cache",
            "category": "developer",
            "path": Path.home() / ".cargo" / "registry" / "cache",
            "description": "Rust Cargo downloaded .crate package archives.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "cargo_git",
            "name": "Cargo Git Clones",
            "category": "developer",
            "path": Path.home() / ".cargo" / "git" / "db",
            "description": "Rust Cargo cached git repository checkouts.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "go_build",
            "name": "Go Build Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "go-build",
            "description": "Go compiler build artifacts and test cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "gradle",
            "name": "Gradle Cache",
            "category": "developer",
            "path": Path.home() / ".gradle" / "caches",
            "description": "Gradle downloaded jars, dependencies, and build outputs.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "r_cache",
            "name": "R Package Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "R",
            "description": "R statistical environment package download cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "vscode_cache",
            "name": "VS Code Cache",
            "category": "developer",
            "path": Path.home() / ".config" / "Code" / "Cache",
            "description": "Visual Studio Code editor GPU and runtime cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "vscode_cached_data",
            "name": "VS Code Cached Data",
            "category": "developer",
            "path": Path.home() / ".config" / "Code" / "CachedData",
            "description": "Visual Studio Code V8 bytecode cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "vscodium_cache",
            "name": "VSCodium Cache",
            "category": "developer",
            "path": Path.home() / ".config" / "VSCodium" / "Cache",
            "description": "VSCodium editor runtime cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "jetbrains_cache",
            "name": "JetBrains IDE Caches",
            "category": "developer",
            "path": Path.home() / ".cache" / "JetBrains",
            "description": "JetBrains IDEs (IntelliJ, PyCharm, CLion) system and index caches.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": False,
        },
        {
            "id": "podman_tmp",
            "name": "Podman Storage Temp",
            "category": "developer",
            "path": Path.home() / ".local" / "share" / "containers" / "storage" / "tmp",
            "description": "Podman container engine build and layer temporary files.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "nextflow_cache",
            "name": "Nextflow Cache",
            "category": "developer",
            "path": Path.home() / ".nextflow" / "cache",
            "description": "Nextflow workflow execution run cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": False,
        },
        {
            "id": "snakemake_cache",
            "name": "Snakemake Conda Cache",
            "category": "developer",
            "path": Path.home() / ".snakemake" / "conda",
            "description": "Snakemake pipeline conda environment cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": False,
        },

        # System & Desktop Junk
        {
            "id": "thumbnails",
            "name": "Desktop Thumbnails",
            "category": "system",
            "path": Path.home() / ".cache" / "thumbnails",
            "description": "GNOME and file manager image/video thumbnail previews. Regenerated as needed.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "trash",
            "name": "Desktop Trash Bin",
            "category": "system",
            "path": Path.home() / ".local" / "share" / "Trash",
            "description": "Files and metadata moved to desktop Trash.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": False,
        },
        {
            "id": "coredump",
            "name": "System Core Dumps",
            "category": "system",
            "path": Path("/var/lib/systemd/coredump"),
            "description": "Crash core dumps stored by systemd in /var/lib/systemd/coredump.",
            "safe_to_clean": True,
            "needs_sudo": True,
            "sudo_command": "sudo rm -rf /var/lib/systemd/coredump/*",
            "default_checked": True,
        },
        {
            "id": "var_crash",
            "name": "Debian/Ubuntu Crash Reports",
            "category": "system",
            "path": Path("/var/crash"),
            "description": "Debian and Ubuntu Apport application crash reports.",
            "safe_to_clean": True,
            "needs_sudo": True,
            "sudo_command": "sudo rm -rf /var/crash/*",
            "default_checked": True,
        },
        {
            "id": "targz_uploads",
            "name": "TarGz Uploads Temp",
            "category": "system",
            "path": Path("/tmp/targz_uploads"),
            "description": "Temporary archives uploaded through TarGz Manager.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        }
    ]

    def __init__(self, target_definitions: Optional[List[Dict[str, Any]]] = None):
        self.TARGET_DEFINITIONS = target_definitions or self.DEFAULT_TARGETS

    @staticmethod
    def get_directory_stats(dir_path: Path, only_extensions: Optional[tuple[str, ...]] = None) -> tuple[int, int]:
        """
        Recursively compute total size in bytes and number of files in directory.
        Does not follow symlinks. If only_extensions is provided, only files
        matching those extensions are counted.
        """
        total_size = 0
        file_count = 0

        if not dir_path.exists():
            return 0, 0

        if dir_path.is_file():
            try:
                if only_extensions and not dir_path.name.endswith(only_extensions):
                    return 0, 0
                return dir_path.stat().st_size, 1
            except Exception:
                return 0, 0

        stack = [dir_path]
        while stack:
            current = stack.pop()
            try:
                with os.scandir(current) as it:
                    for entry in it:
                        try:
                            # Do not follow symlinks
                            if entry.is_symlink():
                                if not only_extensions:
                                    file_count += 1
                                continue
                            if entry.is_dir():
                                if not only_extensions:
                                    stack.append(Path(entry.path))
                            else:
                                if only_extensions and not entry.name.endswith(only_extensions):
                                    continue
                                total_size += entry.stat().st_size
                                file_count += 1
                        except (PermissionError, FileNotFoundError):
                            continue
            except (PermissionError, FileNotFoundError):
                continue

        return total_size, file_count

    def scan(self) -> Dict[str, Any]:
        """
        Scan all known cache targets and return sizes, counts, and summaries.
        """
        results = []
        total_size_bytes = 0
        total_files = 0

        for target in self.TARGET_DEFINITIONS:
            path = Path(target["path"])
            if not path.exists():
                continue

            only_exts = target.get("only_extensions")
            size_bytes, count = self.get_directory_stats(path, only_extensions=only_exts)
            if size_bytes == 0 and count == 0:
                continue

            total_size_bytes += size_bytes
            total_files += count

            needs_sudo = target.get("needs_sudo", False) or Installer.check_needs_sudo(path)
            sudo_cmd = target.get("sudo_command")
            if not sudo_cmd and needs_sudo:
                sudo_cmd = f"sudo rm -rf {shlex.quote(str(path))}/*"

            results.append({
                "id": target["id"],
                "name": target["name"],
                "category": target["category"],
                "path": str(path),
                "description": target["description"],
                "safe_to_clean": target.get("safe_to_clean", True),
                "needs_sudo": needs_sudo,
                "sudo_command": sudo_cmd if needs_sudo else None,
                "default_checked": target.get("default_checked", True),
                "size_bytes": size_bytes,
                "size_formatted": Database.format_size(size_bytes),
                "file_count": count
            })

        return {
            "targets": results,
            "total_size_bytes": total_size_bytes,
            "total_size_formatted": Database.format_size(total_size_bytes),
            "total_files": total_files
        }

    def _clean_with_sudo(
        self,
        target: Dict[str, Any],
        path: Path,
        sudo_password: Optional[str],
        interactive: bool
    ) -> Optional[Dict[str, Any]]:
        """
        Execute privileged clean commands using sudo or root privileges.
        Returns an error dictionary if execution fails, or None on success.
        """
        target_id = target["id"]
        sudo_cmd = target.get("sudo_command") or f"sudo rm -rf {shlex.quote(str(path))}/*"

        if hasattr(os, "geteuid") and os.geteuid() == 0:
            if target_id == "pacman":
                subprocess.run(["pacman", "-Scc", "--noconfirm"], check=False)
            elif target_id == "apt":
                subprocess.run(["apt-get", "clean"], check=False)
            elif target_id == "dnf":
                subprocess.run(["dnf", "clean", "all"], check=False)
            else:
                subprocess.run(["sh", "-c", f"rm -rf {shlex.quote(str(path))}/*"], check=False)
            return None

        if sudo_password:
            if target_id == "pacman":
                sub_cmd = ["pacman", "-Scc", "--noconfirm"]
            elif target_id == "apt":
                sub_cmd = ["apt-get", "clean"]
            elif target_id == "dnf":
                sub_cmd = ["dnf", "clean", "all"]
            else:
                sub_cmd = ["sh", "-c", f"rm -rf {shlex.quote(str(path))}/*"]
            cmd = ["sudo", "-S", "-k"] + sub_cmd
            res = subprocess.run(cmd, input=f"{sudo_password}\n", capture_output=True, text=True)
            if res.returncode != 0:
                err = res.stderr.strip() or res.stdout.strip()
                return {
                    "id": target_id,
                    "name": target["name"],
                    "success": False,
                    "freed_bytes": 0,
                    "freed_formatted": "0 B",
                    "freed_files": 0,
                    "needs_sudo": True,
                    "sudo_command": sudo_cmd,
                    "error": "Incorrect sudo password" if ("incorrect" in err.lower() or "password" in err.lower() or "required" in err.lower()) else (err or "Clean failed")
                }
            return None

        if interactive:
            print(f"\n[sudo] Administrator permissions required for {target['name']}:")
            print(f"  Command: {sudo_cmd}")
            if target_id == "pacman":
                cmd = ["sudo", "pacman", "-Scc"]
            elif target_id == "apt":
                cmd = ["sudo", "apt-get", "clean"]
            elif target_id == "dnf":
                cmd = ["sudo", "dnf", "clean", "all"]
            elif sudo_cmd and not ("*" in sudo_cmd or ";" in sudo_cmd or "|" in sudo_cmd or "&" in sudo_cmd):
                cmd = shlex.split(sudo_cmd)
            else:
                cmd = ["sudo", "sh", "-c", f"rm -rf {shlex.quote(str(path))}/*"]
            res = subprocess.run(cmd)
            if res.returncode != 0:
                return {
                    "id": target_id,
                    "name": target["name"],
                    "success": False,
                    "freed_bytes": 0,
                    "freed_formatted": "0 B",
                    "freed_files": 0,
                    "needs_sudo": True,
                    "sudo_command": sudo_cmd,
                    "error": "Sudo command cancelled or failed"
                }
            return None

        return {
            "id": target_id,
            "name": target["name"],
            "success": False,
            "freed_bytes": 0,
            "freed_formatted": "0 B",
            "freed_files": 0,
            "needs_sudo": True,
            "sudo_command": sudo_cmd,
            "error": f"Root privileges required. Run: {sudo_cmd}"
        }

    def _clean_with_extensions(self, target_id: str, path: Path, only_exts: Any) -> None:
        """
        Clean files in path that match specific extensions, including conda/mamba package clean.
        """
        if "conda" in target_id or "mamba" in target_id:
            conda_bin = shutil.which("conda") or shutil.which("mamba")
            if not conda_bin:
                local_conda = path.parent / "bin" / "conda"
                if local_conda.exists() and os.access(str(local_conda), os.X_OK):
                    conda_bin = str(local_conda)
            if conda_bin:
                try:
                    subprocess.run([conda_bin, "clean", "--tarballs", "-y"], capture_output=True, check=False)
                except Exception:
                    pass

        if path.is_dir():
            for item in path.iterdir():
                try:
                    if item.is_file() and item.name.endswith(only_exts):
                        item.unlink()
                except Exception:
                    continue

    def _clean_user_directory(self, target_id: str, path: Path) -> None:
        """
        Clean unprivileged user-owned files or directory content.
        """
        if target_id == "uv_cache" and shutil.which("uv"):
            subprocess.run(["uv", "cache", "clean"], capture_output=True, check=False)
        else:
            if path.is_file():
                path.unlink()
            else:
                for item in path.iterdir():
                    try:
                        if item.is_dir() and not item.is_symlink():
                            shutil.rmtree(item)
                        else:
                            item.unlink()
                    except Exception:
                        continue

    def clean_target(self, target_id: str, sudo_password: Optional[str] = None, interactive: bool = False) -> Dict[str, Any]:
        """
        Clean an individual cache target by id.
        """
        target = next((t for t in self.TARGET_DEFINITIONS if t["id"] == target_id), None)
        if not target:
            return {
                "id": target_id,
                "name": target_id,
                "success": False,
                "freed_bytes": 0,
                "freed_formatted": "0 B",
                "freed_files": 0,
                "error": f"Unknown target: {target_id}"
            }

        path = Path(target["path"])
        needs_sudo = target.get("needs_sudo", False) or (path.exists() and Installer.check_needs_sudo(path))
        sudo_cmd = target.get("sudo_command")
        if not sudo_cmd and needs_sudo:
            sudo_cmd = f"sudo rm -rf {shlex.quote(str(path))}/*"

        if not path.exists() and not (needs_sudo and sudo_password):
            return {
                "id": target_id,
                "name": target["name"],
                "success": True,
                "freed_bytes": 0,
                "freed_formatted": "0 B",
                "freed_files": 0,
                "error": None
            }

        only_exts = target.get("only_extensions")
        initial_size, initial_files = self.get_directory_stats(path, only_extensions=only_exts)

        try:
            if needs_sudo:
                error_response = self._clean_with_sudo(target, path, sudo_password, interactive)
                if error_response:
                    return error_response
            elif only_exts:
                self._clean_with_extensions(target_id, path, only_exts)
            else:
                self._clean_user_directory(target_id, path)

            new_size, new_files = self.get_directory_stats(path, only_extensions=only_exts)
            freed = max(0, initial_size - new_size)
            files_freed = max(0, initial_files - new_files)

            return {
                "id": target_id,
                "name": target["name"],
                "success": True,
                "freed_bytes": freed,
                "freed_formatted": Database.format_size(freed),
                "freed_files": files_freed,
                "error": None
            }

        except Exception as e:
            return {
                "id": target_id,
                "name": target["name"],
                "success": False,
                "freed_bytes": 0,
                "freed_formatted": "0 B",
                "freed_files": 0,
                "error": str(e)
            }

    def clean(self, target_ids: List[str], sudo_password: Optional[str] = None, interactive: bool = False) -> Dict[str, Any]:
        """
        Clean multiple cache targets by id.
        """
        results = []
        total_freed_bytes = 0
        total_freed_files = 0

        for tid in target_ids:
            res = self.clean_target(tid, sudo_password=sudo_password, interactive=interactive)
            results.append(res)
            if res.get("success"):
                total_freed_bytes += res.get("freed_bytes", 0)
                total_freed_files += res.get("freed_files", 0)

        return {
            "freed_bytes": total_freed_bytes,
            "freed_formatted": Database.format_size(total_freed_bytes),
            "freed_files": total_freed_files,
            "results": results
        }
