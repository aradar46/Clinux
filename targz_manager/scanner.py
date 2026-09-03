import os
import re
import stat
from pathlib import Path
from typing import List, Dict, Optional, Any, Set

from .db import Database
from .installer import Installer, DEFAULT_OPT_DIR, DEFAULT_DESKTOP_DIR, DEFAULT_BIN_DIR
from .utils import compute_directory_size


class SystemScanner:
    _icon_cache: Dict[str, Optional[str]] = {}

    def __init__(self, db: Database, installer: Optional[Installer] = None):
        self.db = db
        self.installer = installer or Installer(db)

    @classmethod
    def find_system_icon(cls, icon_name: str) -> Optional[str]:
        """Search system XDG icon theme paths and pixmaps for an icon name with caching"""
        if not icon_name or icon_name in {"application-x-executable", "applications-other"}:
            return None

        icon_name = icon_name.strip('"\'; ')

        if icon_name in cls._icon_cache:
            return cls._icon_cache[icon_name]

        if icon_name.startswith("/"):
            p = Path(icon_name)
            if p.exists() and p.is_file():
                cls._icon_cache[icon_name] = str(p.resolve())
                return str(p.resolve())
            for ext in [".png", ".svg", ".xpm", ".ico"]:
                cand = Path(icon_name + ext)
                if cand.exists():
                    cls._icon_cache[icon_name] = str(cand.resolve())
                    return str(cand.resolve())
            cls._icon_cache[icon_name] = None
            return None

        clean_stem = Path(icon_name).stem.lower()

        direct_checks = [
            Path(f"/usr/share/pixmaps/{clean_stem}.png"),
            Path(f"/usr/share/pixmaps/{clean_stem}.svg"),
            Path(f"/usr/share/pixmaps/{clean_stem}.xpm"),
            Path.home() / f".local/share/icons/hicolor/scalable/apps/{clean_stem}.svg",
            Path.home() / f".local/share/icons/hicolor/128x128/apps/{clean_stem}.png",
            Path.home() / f".local/share/icons/hicolor/48x48/apps/{clean_stem}.png",
            Path(f"/usr/share/icons/hicolor/scalable/apps/{clean_stem}.svg"),
            Path(f"/usr/share/icons/hicolor/128x128/apps/{clean_stem}.png"),
            Path(f"/usr/share/icons/hicolor/64x64/apps/{clean_stem}.png"),
            Path(f"/usr/share/icons/hicolor/48x48/apps/{clean_stem}.png"),
            Path(f"/usr/share/icons/hicolor/32x32/apps/{clean_stem}.png"),
            Path.home() / f".icons/{clean_stem}.png",
            Path.home() / f".icons/{clean_stem}.svg"
        ]

        for cand in direct_checks:
            if cand.exists() and cand.is_file():
                cls._icon_cache[icon_name] = str(cand.resolve())
                return str(cand.resolve())

        for base in [Path.home() / ".local/share/icons", Path("/usr/share/icons")]:
            if not base.exists():
                continue
            for theme_dir in base.iterdir():
                if not theme_dir.is_dir():
                    continue
                for size in ["scalable", "128x128", "64x64", "48x48"]:
                    cand_svg = theme_dir / size / "apps" / f"{clean_stem}.svg"
                    if cand_svg.exists():
                        cls._icon_cache[icon_name] = str(cand_svg.resolve())
                        return str(cand_svg.resolve())
                    cand_png = theme_dir / size / "apps" / f"{clean_stem}.png"
                    if cand_png.exists():
                        cls._icon_cache[icon_name] = str(cand_png.resolve())
                        return str(cand_png.resolve())

        cls._icon_cache[icon_name] = None
        return None

    @staticmethod
    def get_search_roots() -> List[Path]:
        """Return list of standard directories where portable/manual apps reside"""
        home = Path.home()
        roots = [
            DEFAULT_OPT_DIR,
            Path("/opt"),
            Path("/usr/local/opt"),
            home / "opt",
            home / "Applications",
            home / "Apps",
            home / "Software",
            home / "programs",
            home / "AppImages"
        ]
        return [r for r in roots if r.exists() and r.is_dir()]

    def scan_desktop_entries(self) -> List[Dict[str, Any]]:
        """Scan ~/.local/share/applications for .desktop files pointing to non-system / manual paths"""
        desktop_dir = DEFAULT_DESKTOP_DIR
        if not desktop_dir.exists():
            return []

        results = []
        ignored_names = {"targz-manager.desktop", "mimeapps.list"}
        system_prefixes = ("/usr/bin", "/bin", "/usr/games", "/usr/sbin", "/sbin")

        for d_file in desktop_dir.glob("*.desktop"):
            if d_file.name in ignored_names:
                continue

            entry_data = self._parse_desktop_file(d_file)
            if not entry_data or not entry_data.get("exec_clean"):
                continue

            exec_path = entry_data["exec_clean"]

            if any(exec_path.startswith(prefix) for prefix in system_prefixes):
                if not (exec_path.startswith("/opt") or str(Path.home()) in exec_path):
                    continue

            exec_p = Path(exec_path)
            if not exec_p.exists():
                exec_p = Path(os.path.expanduser(exec_path))
                if not exec_p.exists():
                    continue

            install_dir = exec_p.parent
            if install_dir.name in {"bin", "lib", "libexec", "usr"}:
                install_dir = install_dir.parent

            icon_path = entry_data.get("icon_raw")
            resolved_icon = None
            if icon_path:
                resolved_icon = self.find_system_icon(icon_path)
            if not resolved_icon:
                cand_icons = self.installer.scan_directory_candidates(install_dir, entry_data.get("name", ""))
                if cand_icons["icons"]:
                    resolved_icon = cand_icons["icons"][0]["full_path"]

            slug = self.installer.slugify(entry_data.get("name") or d_file.stem)
            disp_name = entry_data.get("name") or d_file.stem.replace('-', ' ').title()

            results.append({
                "source": "desktop_file",
                "desktop_file": str(d_file.resolve()),
                "name": slug,
                "display_name": disp_name,
                "version": entry_data.get("version") or self._extract_version(str(install_dir)) or "1.0.0",
                "category": entry_data.get("category", "Utility"),
                "description": entry_data.get("comment", ""),
                "install_path": str(install_dir.resolve()),
                "executable_path": str(exec_p.resolve()),
                "icon_path": resolved_icon,
                "terminal": entry_data.get("terminal", False),
                "discovery_reason": f"From desktop shortcut: {d_file.name}"
            })

        return results

    def _parse_desktop_file(self, path: Path) -> Optional[Dict[str, Any]]:
        """Parse FreeDesktop .desktop entry file"""
        try:
            with open(path, "r", encoding="utf-8", errors="ignore") as f:
                lines = f.readlines()
        except Exception:
            return None

        data = {}
        in_desktop_entry = False

        for line in lines:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if line == "[Desktop Entry]":
                in_desktop_entry = True
                continue
            elif line.startswith("[") and line.endswith("]"):
                in_desktop_entry = False
                continue

            if in_desktop_entry and "=" in line:
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip()
                data[k] = v

        if not data.get("Exec"):
            return None

        raw_exec = data["Exec"]
        clean_exec = re.sub(r'%[a-zA-Z]', '', raw_exec).strip()
        if clean_exec.startswith("env "):
            parts = clean_exec.split()
            for p in parts[1:]:
                if not "=" in p:
                    clean_exec = p
                    break
        clean_exec = clean_exec.strip('"\'; ')
        clean_exec = os.path.expanduser(clean_exec)
        if " " in clean_exec:
            first_token = clean_exec.split()[0]
            if Path(first_token).exists():
                clean_exec = first_token

        category = "Utility"
        if data.get("Categories"):
            cats = [c.strip() for c in data["Categories"].split(";") if c.strip()]
            for c in cats:
                if c in {"Development", "Graphics", "AudioVideo", "Network", "Game", "Office", "System", "Utility"}:
                    category = c
                    break

        return {
            "name": data.get("Name"),
            "exec_raw": raw_exec,
            "exec_clean": clean_exec,
            "icon_raw": data.get("Icon"),
            "comment": data.get("Comment", ""),
            "category": category,
            "version": data.get("X-AppImage-Version") or data.get("Version"),
            "terminal": data.get("Terminal", "false").lower() == "true"
        }

    @staticmethod
    def _extract_version(text: str) -> Optional[str]:
        ver_match = re.search(r'[-_.]v?(\d+(\.\d+)+([-_.]\w+)?)', text)
        if ver_match:
            return ver_match.group(1).lstrip('v')
        return None

    def auto_resolve_directory(self, dir_path: str) -> Dict[str, Any]:
        """Auto-detect executable, icon, display name, version, and category for any folder on the system"""
        target = Path(dir_path).expanduser().resolve()
        if not target.exists():
            return {"error": f"Directory not found: {dir_path}"}

        if target.is_file():
            slug, ver, disp = self.installer.guess_name_and_version(target.name)
            icon = self.find_system_icon(slug)
            return {
                "name": slug,
                "display_name": disp,
                "version": ver or "1.0.0",
                "category": "Utility",
                "install_path": str(target.parent),
                "executable_path": str(target),
                "icon_path": icon,
                "executables": [{"path": target.name, "full_path": str(target), "score": 100}],
                "icons": [],
                "size_bytes": target.stat().st_size,
                "size_formatted": Database.format_size(target.stat().st_size)
            }

        folder_name = target.name
        slug, guessed_ver, disp_name = self.installer.guess_name_and_version(folder_name)

        candidates = self.installer.scan_directory_candidates(target, slug)
        best_exec = candidates["executables"][0]["full_path"] if candidates["executables"] else None
        best_icon = candidates["icons"][0]["full_path"] if candidates["icons"] else None

        matching_desktop = None
        for d in DEFAULT_DESKTOP_DIR.glob("*.desktop"):
            if slug in d.name.lower() or folder_name.lower() in d.name.lower():
                parsed = self._parse_desktop_file(d)
                if parsed:
                    matching_desktop = parsed
                    break

        if matching_desktop:
            disp_name = matching_desktop.get("name") or disp_name
            if not best_icon and matching_desktop.get("icon_raw"):
                best_icon = self.find_system_icon(matching_desktop["icon_raw"])

        if not best_icon:
            best_icon = self.find_system_icon(slug) or self.find_system_icon(folder_name)

        category = "Utility"
        lower_slug = slug.lower()
        if any(k in lower_slug for k in ["ide", "code", "studio", "dev", "git", "pycharm", "clion", "rust", "nvim", "vim", "sublime", "quarto", "cytoscape"]):
            category = "Development"
        elif any(k in lower_slug for k in ["draw", "paint", "gimp", "inkscape", "blender", "krita", "photo", "vial", "logseq"]):
            category = "Graphics"
        elif any(k in lower_slug for k in ["player", "music", "video", "vlc", "mpv", "audacity", "obs", "sound"]):
            category = "AudioVideo"
        elif any(k in lower_slug for k in ["browser", "firefox", "chrome", "torrent", "download", "discord", "telegram", "slack", "mail", "postnet"]):
            category = "Network"
        elif any(k in lower_slug for k in ["game", "steam", "emu", "retro", "minecraft"]):
            category = "Game"

        # Fast directory size calculation using os.scandir (avoiding slow Path.rglob)
        calc_size = compute_directory_size(target)

        needs_sudo = not os.access(str(target), os.W_OK)

        return {
            "name": slug,
            "display_name": disp_name,
            "version": guessed_ver or "1.0.0",
            "category": category,
            "install_path": str(target),
            "executable_path": best_exec,
            "icon_path": best_icon,
            "executables": candidates["executables"],
            "icons": candidates["icons"],
            "size_bytes": calc_size,
            "size_formatted": Database.format_size(calc_size),
            "needs_sudo": needs_sudo
        }

    def discover_unmanaged_apps(self) -> List[Dict[str, Any]]:
        """Scan system directories and desktop shortcuts to find unmanaged portable applications"""
        managed_apps = self.db.list_apps()
        managed_paths: Set[str] = {str(Path(a["install_path"]).resolve()) for a in managed_apps}
        managed_execs: Set[str] = {str(Path(a["executable_path"]).resolve()) for a in managed_apps}
        managed_names: Set[str] = {a["name"].lower() for a in managed_apps}

        discovered: List[Dict[str, Any]] = []
        seen_paths: Set[str] = set()

        discovered.extend(self._discover_from_desktop_entries(managed_paths, managed_execs, managed_names, seen_paths))
        discovered.extend(self._discover_from_directory_scans(managed_paths, managed_execs, managed_names, seen_paths))
        discovered.extend(self._discover_from_downloads(managed_names, seen_paths))

        self._annotate_ignored_status(discovered)

        return discovered

    def _discover_from_desktop_entries(
        self, managed_paths: Set[str], managed_execs: Set[str], managed_names: Set[str], seen_paths: Set[str]
    ) -> List[Dict[str, Any]]:
        discovered: List[Dict[str, Any]] = []
        desktop_candidates = self.scan_desktop_entries()

        for cand in desktop_candidates:
            inst_p = str(Path(cand["install_path"]).resolve())
            exec_p = str(Path(cand["executable_path"]).resolve())
            name_k = cand["name"].lower()

            if inst_p in managed_paths or exec_p in managed_execs or name_k in managed_names:
                continue
            if inst_p in seen_paths:
                continue

            seen_paths.add(inst_p)
            calc_size = 0
            needs_sudo = not os.access(inst_p, os.W_OK) if Path(inst_p).exists() else False
            try:
                p_dir = Path(inst_p)
                if p_dir.exists() and p_dir.is_dir():
                    calc_size = compute_directory_size(p_dir)
                elif Path(exec_p).exists():
                    calc_size = Path(exec_p).stat().st_size
            except Exception:
                pass

            cand["size_bytes"] = calc_size
            cand["size_formatted"] = Database.format_size(calc_size)
            cand["needs_sudo"] = needs_sudo
            discovered.append(cand)

        return discovered

    def _discover_from_directory_scans(
        self, managed_paths: Set[str], managed_execs: Set[str], managed_names: Set[str], seen_paths: Set[str]
    ) -> List[Dict[str, Any]]:
        discovered: List[Dict[str, Any]] = []
        ignored_dir_names = {
            "containerd", "stacks", "node_modules", "__pycache__", ".trash", "lost+found",
            "hidden", "temp", "tmp", "logs", "cache", ".git", ".local", "dist-packages", "site-packages"
        }

        roots = self.get_search_roots()
        for root in roots:
            try:
                for entry in root.iterdir():
                    if not entry.is_dir() or entry.name.startswith(".") or entry.name.lower() in ignored_dir_names:
                        continue

                    entry_res = str(entry.resolve())
                    if entry_res in managed_paths or entry_res in seen_paths:
                        continue

                    res = self.auto_resolve_directory(entry_res)
                    if res.get("executable_path"):
                        exec_res = str(Path(res["executable_path"]).resolve())
                        if exec_res in managed_execs:
                            continue

                        name_k = res["name"].lower()
                        if name_k in managed_names:
                            continue

                        seen_paths.add(entry_res)
                        discovered.append({
                            "source": "directory_scan",
                            "name": res["name"],
                            "display_name": res["display_name"],
                            "version": res["version"],
                            "category": res["category"],
                            "description": f"Found in {root.name}/",
                            "install_path": entry_res,
                            "executable_path": res["executable_path"],
                            "icon_path": res["icon_path"],
                            "size_bytes": res["size_bytes"],
                            "size_formatted": res["size_formatted"],
                            "discovery_reason": f"Discovered in {root}"
                        })
            except PermissionError:
                pass

        return discovered

    def _discover_from_downloads(
        self, managed_names: Set[str], seen_paths: Set[str]
    ) -> List[Dict[str, Any]]:
        discovered: List[Dict[str, Any]] = []
        downloads_dir = Path.home() / "Downloads"

        if downloads_dir.exists():
            for archive in downloads_dir.glob("*.tar.gz"):
                name, ver, disp = self.installer.guess_name_and_version(archive.name)
                slug = self.installer.slugify(name)
                arch_res = str(archive.resolve())
                if slug not in managed_names and arch_res not in seen_paths:
                    seen_paths.add(arch_res)
                    discovered.append({
                        "source": "archive_file",
                        "name": slug,
                        "display_name": disp,
                        "version": ver,
                        "category": "Utility",
                        "description": "Ready-to-install tarball archive in Downloads/",
                        "archive_path": arch_res,
                        "install_path": str(DEFAULT_OPT_DIR / slug),
                        "executable_path": "",
                        "icon_path": None,
                        "size_bytes": archive.stat().st_size,
                        "size_formatted": Database.format_size(archive.stat().st_size),
                        "is_tarball_archive": True,
                        "discovery_reason": "Found in ~/Downloads"
                    })

        return discovered

    def _annotate_ignored_status(self, discovered: List[Dict[str, Any]]) -> None:
        ignored_keys = {row["key"] for row in self.db.list_ignored_discoveries()}
        for item in discovered:
            key = item.get("archive_path") or item.get("install_path")
            item["ignore_key"] = key
            item["ignored"] = key in ignored_keys
