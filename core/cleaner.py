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
        # Miniforge
        {
            "id": "miniforge_pkgs",
            "name": "Miniforge Package Cache",
            "category": "package_managers",
            "path": Path.home() / "miniforge3" / "pkgs",
            "description": "Downloaded conda package archives, unused packages, and index cache in Miniforge.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "miniforge_pkgs_alt",
            "name": "Miniforge Package Cache",
            "category": "package_managers",
            "path": Path.home() / "miniforge" / "pkgs",
            "description": "Downloaded conda package archives, unused packages, and index cache in Miniforge.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        # Miniconda
        {
            "id": "miniconda_pkgs",
            "name": "Miniconda Package Cache",
            "category": "package_managers",
            "path": Path.home() / "miniconda3" / "pkgs",
            "description": "Downloaded conda package archives, unused packages, and index cache in Miniconda.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "miniconda_pkgs_alt",
            "name": "Miniconda Package Cache",
            "category": "package_managers",
            "path": Path.home() / "miniconda" / "pkgs",
            "description": "Downloaded conda package archives, unused packages, and index cache in Miniconda.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        # Mambaforge
        {
            "id": "mambaforge_pkgs",
            "name": "Mambaforge Package Cache",
            "category": "package_managers",
            "path": Path.home() / "mambaforge" / "pkgs",
            "description": "Downloaded conda package archives, unused packages, and index cache in Mambaforge.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        # Anaconda
        {
            "id": "anaconda3_pkgs",
            "name": "Anaconda Package Cache",
            "category": "package_managers",
            "path": Path.home() / "anaconda3" / "pkgs",
            "description": "Downloaded conda package archives, unused packages, and index cache in Anaconda.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "anaconda_pkgs_alt",
            "name": "Anaconda Package Cache",
            "category": "package_managers",
            "path": Path.home() / "anaconda" / "pkgs",
            "description": "Downloaded conda package archives, unused packages, and index cache in Anaconda.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        # User-level Conda / Mamba / Micromamba package caches
        {
            "id": "conda_pkgs",
            "name": "Conda User Package Cache",
            "category": "package_managers",
            "path": Path.home() / ".conda" / "pkgs",
            "description": "User-level downloaded conda package archives (.conda, .tar.bz2).",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "mamba_pkgs",
            "name": "Mamba User Package Cache",
            "category": "package_managers",
            "path": Path.home() / ".mamba" / "pkgs",
            "description": "User-level downloaded mamba package archives (.conda, .tar.bz2).",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "micromamba_pkgs",
            "name": "Micromamba Package Cache",
            "category": "package_managers",
            "path": Path.home() / ".micromamba" / "pkgs",
            "description": "Downloaded micromamba package archives (.conda, .tar.bz2).",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        # System Conda
        {
            "id": "system_conda_pkgs",
            "name": "System Conda Package Cache",
            "category": "package_managers",
            "path": Path("/opt/conda/pkgs"),
            "description": "System-wide conda package archives in /opt/conda.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": True,
            "default_checked": False,
        },
        {
            "id": "system_miniforge_pkgs",
            "name": "System Miniforge Package Cache",
            "category": "package_managers",
            "path": Path("/opt/miniforge3/pkgs"),
            "description": "System-wide miniforge package archives in /opt/miniforge3.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": True,
            "default_checked": False,
        },
        {
            "id": "system_miniconda_pkgs",
            "name": "System Miniconda Package Cache",
            "category": "package_managers",
            "path": Path("/opt/miniconda3/pkgs"),
            "description": "System-wide miniconda package archives in /opt/miniconda3.",
            "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
            "safe_to_clean": True,
            "needs_sudo": True,
            "default_checked": False,
        },
        # Repodata, Index, HTTP & Tool Caches
        {
            "id": "conda_http_cache",
            "name": "Conda HTTP & Index Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "conda",
            "description": "Conda channel repodata, notices, and HTTP cache files.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "mamba_http_cache",
            "name": "Mamba Repodata Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "mamba",
            "description": "Mamba channel repodata cache and metadata.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "condanest_cache",
            "name": "Conda Nest Log & State Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "condanest",
            "description": "Conda nest logs and temporary state cache.",
            "safe_to_clean": True,
            "needs_sudo": False,
            "default_checked": True,
        },
        {
            "id": "pixi_rattler_cache",
            "name": "Pixi / Rattler Package Cache",
            "category": "developer",
            "path": Path.home() / ".cache" / "rattler" / "cache",
            "description": "Pixi and rattler package archives and repodata cache.",
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
        self._custom_targets = target_definitions is not None
        self.TARGET_DEFINITIONS = target_definitions or self.DEFAULT_TARGETS

    @staticmethod
    def find_conda_binaries() -> Dict[str, str]:
        """
        Locate all available conda/mamba/micromamba/pixi binaries across PATH and standard paths.
        """
        bins = {}
        for name in ("mamba", "conda", "micromamba", "pixi"):
            p = shutil.which(name)
            if p:
                bins[name] = p

        candidates = [
            ("miniforge", Path.home() / "miniforge3" / "bin"),
            ("miniforge", Path.home() / "miniforge" / "bin"),
            ("miniconda", Path.home() / "miniconda3" / "bin"),
            ("miniconda", Path.home() / "miniconda" / "bin"),
            ("mambaforge", Path.home() / "mambaforge" / "bin"),
            ("anaconda", Path.home() / "anaconda3" / "bin"),
            ("anaconda", Path.home() / "anaconda" / "bin"),
            ("micromamba", Path.home() / ".local" / "bin"),
            ("micromamba", Path.home() / ".micromamba" / "bin"),
            ("pixi", Path.home() / ".local" / "bin"),
            ("pixi", Path.home() / ".pixi" / "bin"),
            ("system_conda", Path("/opt/conda/bin")),
            ("system_miniforge", Path("/opt/miniforge3/bin")),
            ("system_miniconda", Path("/opt/miniconda3/bin")),
        ]
        for _, cdir in candidates:
            for bname in ("mamba", "conda", "micromamba", "pixi"):
                bp = cdir / bname
                if bp.exists() and bp.is_file() and os.access(str(bp), os.X_OK):
                    if bname not in bins:
                        bins[bname] = str(bp)
        return bins

    def find_conda_executable(self, preferred_path: Optional[Path] = None) -> Optional[str]:
        """
        Return the most suitable conda/mamba binary, checking preferred_path first.
        """
        if preferred_path:
            for parent_dir in (preferred_path.parent, preferred_path):
                for bname in ("mamba", "conda", "micromamba"):
                    for sub in ("bin", "condabin", ""):
                        candidate = (parent_dir / sub / bname) if sub else (parent_dir / bname)
                        if candidate.exists() and candidate.is_file() and os.access(str(candidate), os.X_OK):
                            return str(candidate)

        bins = self.find_conda_binaries()
        return bins.get("mamba") or bins.get("conda") or bins.get("micromamba") or bins.get("pixi")

    def discover_conda_targets(self) -> List[Dict[str, Any]]:
        """
        Dynamically discover Conda/Mamba roots and package caches from active runtimes and filesystem.
        """
        discovered = []
        seen_paths = set()

        # 1. Inspect conda info --json if binary exists
        c_bin = self.find_conda_executable()
        if c_bin:
            try:
                res = subprocess.run([c_bin, "info", "--json"], capture_output=True, text=True, timeout=2.5)
                if res.returncode == 0:
                    info = json.loads(res.stdout)
                    for pkg_dir in info.get("pkgs_dirs", []):
                        p = Path(pkg_dir)
                        if p.exists() and p.is_dir() and str(p.resolve()) not in seen_paths:
                            seen_paths.add(str(p.resolve()))
                            discovered.append({
                                "id": f"dyn_conda_{p.name}_{abs(hash(str(p))) % 10000}",
                                "name": f"Conda Package Cache ({p.parent.name})",
                                "category": "package_managers",
                                "path": p,
                                "description": f"Configured conda package cache in {p}.",
                                "only_extensions": (".tar.bz2", ".conda", ".tmp", ".lock", ".mamba_trash"),
                                "safe_to_clean": True,
                                "needs_sudo": Installer.check_needs_sudo(p),
                                "default_checked": True,
                            })
            except Exception:
                pass

        return discovered

    @staticmethod
    def get_conda_dry_run_clean_size(conda_bin: str) -> tuple[int, int]:
        """
        Query conda clean dry run for exact reclaimable unused package and tarball size.
        """
        try:
            res = subprocess.run(
                [conda_bin, "clean", "--dry-run", "--json", "--all"],
                capture_output=True,
                text=True,
                timeout=2.5,
            )
            if res.returncode == 0:
                data = json.loads(res.stdout)
                tarballs_info = data.get("tarballs", {})
                pkgs_info = data.get("packages", {})
                t_bytes = tarballs_info.get("total_size", 0)
                p_bytes = pkgs_info.get("total_size", 0)
                t_files = sum(len(v) for v in tarballs_info.get("pkgs_dirs", {}).values())
                p_files = sum(len(v) for v in pkgs_info.get("pkgs_dirs", {}).values())
                idx_files = len(data.get("index_cache", {}).get("files", []))
                return (t_bytes + p_bytes), (t_files + p_files + idx_files)
        except Exception:
            pass
        return 0, 0

    @staticmethod
    def get_directory_stats(dir_path: Path, only_extensions: Optional[tuple[str, ...]] = None) -> tuple[int, int]:
        """
        Recursively compute total size in bytes and number of files in directory.
        Does not follow symlinks. If only_extensions is provided, only files
        matching those extensions (or specific cache subdirs) are counted.
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
                                # Recurse into cache/temp subdirectories even when only_extensions is set
                                if not only_extensions or entry.name in ("cache", ".trash", "tmp", "trash"):
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

    def get_all_targets(self) -> List[Dict[str, Any]]:
        """
        Return static targets combined with dynamically discovered Conda/Mamba targets.
        """
        all_targets = list(self.TARGET_DEFINITIONS)
        if self._custom_targets:
            return all_targets

        known_resolved = {str(Path(t["path"]).resolve()) for t in all_targets if Path(t["path"]).exists()}

        try:
            for dyn in self.discover_conda_targets():
                resolved = str(Path(dyn["path"]).resolve())
                if resolved not in known_resolved:
                    all_targets.append(dyn)
                    known_resolved.add(resolved)
        except Exception:
            pass

        return all_targets

    def scan(self) -> Dict[str, Any]:
        """
        Scan all known and discovered cache targets and return sizes, counts, and summaries.
        """
        results = []
        total_size_bytes = 0
        total_files = 0

        # Build target list: static targets + dynamically discovered conda/mamba targets
        all_targets = self.get_all_targets()

        # Check conda clean dry run once if available
        conda_bin = self.find_conda_executable()
        conda_clean_bytes, conda_clean_count = (0, 0)
        if conda_bin:
            conda_clean_bytes, conda_clean_count = self.get_conda_dry_run_clean_size(conda_bin)

        applied_conda_clean = False

        for target in all_targets:
            path = Path(target["path"])
            if not path.exists():
                continue

            only_exts = target.get("only_extensions")
            size_bytes, count = self.get_directory_stats(path, only_extensions=only_exts)

            # If this is an active conda pkgs cache and dry run found unused packages/tarballs
            is_conda_pkg = ("conda" in target["id"] or "mamba" in target["id"]) and only_exts
            if is_conda_pkg and not applied_conda_clean and conda_clean_bytes > 0:
                size_bytes += conda_clean_bytes
                count += conda_clean_count
                applied_conda_clean = True

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
            conda_bin = self.find_conda_executable(preferred_path=path)
            if conda_bin:
                try:
                    subprocess.run([conda_bin, "clean", "--all", "-y"], capture_output=True, check=False)
                except Exception:
                    pass

        if path.is_dir():
            for item in path.iterdir():
                try:
                    if item.is_file() and item.name.endswith(only_exts):
                        item.unlink()
                    elif item.is_dir() and item.name in ("cache", ".trash", "trash"):
                        shutil.rmtree(item, ignore_errors=True)
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
        if not target and not self._custom_targets:
            target = next((t for t in self.discover_conda_targets() if t["id"] == target_id), None)
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
        is_conda_pkg = ("conda" in target_id or "mamba" in target_id) and only_exts
        if is_conda_pkg:
            initial_size, initial_files = self.get_directory_stats(path)
        else:
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

            if is_conda_pkg:
                new_size, new_files = self.get_directory_stats(path)
            else:
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
