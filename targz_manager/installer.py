import os
import re
import stat
import shutil
import tarfile
import zipfile
import tempfile
import subprocess
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

from .db import Database

DEFAULT_OPT_DIR = Path.home() / ".local" / "opt"
DEFAULT_BIN_DIR = Path.home() / ".local" / "bin"
DEFAULT_DESKTOP_DIR = Path.home() / ".local" / "share" / "applications"
DEFAULT_ICONS_DIR = Path.home() / ".local" / "share" / "icons"


class ArchiveError(Exception):
    pass


class Installer:
    def __init__(self, db: Optional[Database] = None):
        self.db = db or Database()
        DEFAULT_OPT_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_BIN_DIR.mkdir(parents=True, exist_ok=True)
        DEFAULT_DESKTOP_DIR.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def check_needs_sudo(path: Any) -> bool:
        """Check if path or its parent directory is not writable by current user"""
        try:
            p = Path(path).expanduser().resolve()
            if p.exists():
                return not os.access(str(p), os.W_OK)
            parent = p.parent
            while not parent.exists() and parent != parent.parent:
                parent = parent.parent
            return not os.access(str(parent), os.W_OK)
        except Exception:
            return False

    @classmethod
    def run_elevated_rm(cls, path: Any) -> bool:
        """Delete a directory or file using pkexec / sudo if root permissions are required"""
        p = Path(path).resolve()
        if not p.exists():
            return True
        if not cls.check_needs_sudo(p):
            if p.is_dir():
                shutil.rmtree(p)
            else:
                p.unlink()
            return True

        if shutil.which("pkexec"):
            res = subprocess.run(["pkexec", "rm", "-rf", str(p)], capture_output=True, text=True)
            if res.returncode == 0:
                return True
            raise ArchiveError(f"Root permission required. Authentication failed: {res.stderr.strip() or 'Cancelled'}")
        raise ArchiveError(f"Root permission required to delete {p}. Run in terminal: sudo rm -rf \"{p}\"")

    @classmethod
    def run_elevated_mv(cls, src: Any, dst: Any) -> bool:
        """Move directory or file using pkexec if root permissions are required"""
        src_p = Path(src).resolve()
        dst_p = Path(dst).resolve()
        if not cls.check_needs_sudo(src_p) and not cls.check_needs_sudo(dst_p.parent) and (not dst_p.exists() or not cls.check_needs_sudo(dst_p)):
            if dst_p.exists():
                shutil.rmtree(dst_p) if dst_p.is_dir() else dst_p.unlink()
            shutil.move(str(src_p), str(dst_p))
            return True

        if shutil.which("pkexec"):
            if dst_p.exists():
                subprocess.run(["pkexec", "rm", "-rf", str(dst_p)], check=False)
            res = subprocess.run(["pkexec", "mv", str(src_p), str(dst_p)], capture_output=True, text=True)
            if res.returncode == 0:
                return True
            raise ArchiveError(f"Root permission required. Authentication failed: {res.stderr.strip() or 'Cancelled'}")
        raise ArchiveError(f"Root permission required to install/move to {dst_p}. Run in terminal: sudo mv \"{src_p}\" \"{dst_p}\"")

    @staticmethod
    def slugify(text: str) -> str:
        """Convert name into clean directory and desktop filename slug"""
        text = text.lower().strip()
        text = re.sub(r'[^\w\s-]', '', text)
        text = re.sub(r'[-\s]+', '-', text)
        return text.strip('-') or 'app'

    @staticmethod
    def guess_name_and_version(filename: str) -> Tuple[str, str]:
        """Guess application name and version from archive filename"""
        base = Path(filename).name
        for ext in ['.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz', '.tar', '.zip']:
            if base.lower().endswith(ext):
                base = base[:-len(ext)]
                break

        clean_base = re.sub(r'[-_](linux|x86_64|x64|amd64|arm64|aarch64|i386|i686|64bit|32bit|portable|release|bin|bundle|appimage)', '', base, flags=re.IGNORECASE)

        ver_match = re.search(r'[-_.]v?(\d+(\.\d+)+([-_.]\w+)?)', clean_base)
        if ver_match:
            version = ver_match.group(1).lstrip('v')
            name = clean_base[:ver_match.start()].strip('-_ .')
        else:
            version = "1.0.0"
            name = clean_base

        if not name:
            name = base

        display_name = name.replace('-', ' ').replace('_', ' ').title()
        return name, version, display_name

    def inspect_archive(self, archive_path: str) -> Dict[str, Any]:
        """Inspect archive without extracting, identifying top-level folder, executables, icons, and size"""
        path = Path(archive_path)
        if not path.is_file():
            raise ArchiveError(f"Archive file not found: {archive_path}")

        name, version, display_name = self.guess_name_and_version(path.name)
        members = []
        is_zip = False

        if zipfile.is_zipfile(str(path)):
            is_zip = True
            try:
                with zipfile.ZipFile(str(path), 'r') as zf:
                    for info in zf.infolist():
                        members.append({
                            "name": info.filename.rstrip('/'),
                            "is_dir": info.is_dir(),
                            "size": info.file_size,
                            "mode": info.external_attr >> 16
                        })
            except Exception as e:
                raise ArchiveError(f"Failed to read zip archive: {e}")
        else:
            try:
                with tarfile.open(str(path), 'r:*') as tf:
                    for member in tf.getmembers():
                        members.append({
                            "name": member.name.rstrip('/'),
                            "is_dir": member.isdir(),
                            "size": member.size,
                            "mode": member.mode
                        })
            except Exception as e:
                raise ArchiveError(f"Failed to read tar archive: {e}")

        if not members:
            raise ArchiveError("Archive is empty")

        total_uncompressed_size = sum(m["size"] for m in members)

        root_prefixes = set()
        for m in members:
            parts = m["name"].split('/')
            if parts and parts[0]:
                root_prefixes.add(parts[0])

        single_root = None
        has_wrapper = False
        if len(root_prefixes) == 1:
            candidate = list(root_prefixes)[0]
            if len([m for m in members if m["name"].startswith(candidate + '/') or m["name"] == candidate]) == len(members):
                single_root = candidate
                has_wrapper = True

        if single_root:
            r_name, r_ver, r_disp = self.guess_name_and_version(single_root)
            if r_name and len(r_name) > 1:
                name = r_name
                version = r_ver or version
                display_name = r_disp

        executables = []
        icons = []

        for m in members:
            if m["is_dir"]:
                continue
            m_name = m["name"]
            rel_name = m_name
            if has_wrapper and single_root and m_name.startswith(single_root + '/'):
                rel_name = m_name[len(single_root) + 1:]

            filename = Path(rel_name).name
            lower_name = filename.lower()
            lower_rel = rel_name.lower()

            mode = m.get("mode", 0)
            is_exec_mode = bool(mode & 0o111) if mode else False
            score = 0

            ignored_exts = {'.txt', '.md', '.html', '.css', '.js', '.json', '.xml', '.png', '.jpg', '.svg', '.so', '.a', '.h', '.c', '.cpp', '.pyc', '.mo', '.po', '.desktop', '.man', '.1', '.gz', '.zip'}
            ext = Path(filename).suffix.lower()

            if ext not in ignored_exts:
                if is_exec_mode:
                    score += 50
                if lower_name == name.lower():
                    score += 60
                elif lower_name.startswith(name.lower()):
                    score += 40
                if rel_name.startswith("bin/"):
                    score += 30
                if ext in {'.sh', '.bin', '.appimage'}:
                    score += 20
                if '/' not in rel_name:
                    score += 15

                if score > 0 or is_exec_mode:
                    executables.append({
                        "path": rel_name,
                        "orig_path": m_name,
                        "score": score,
                        "is_exec_bit": is_exec_mode,
                        "size": m["size"]
                    })

            if ext in {'.png', '.svg', '.ico', '.xpm'}:
                icon_score = 10
                if any(k in lower_rel for k in ['icon', 'logo', 'pixmap', 'hicolor', 'scalable']):
                    icon_score += 40
                if name.lower() in lower_name:
                    icon_score += 30
                if ext == '.svg':
                    icon_score += 10
                icons.append({
                    "path": rel_name,
                    "orig_path": m_name,
                    "score": icon_score,
                    "size": m["size"]
                })

        executables.sort(key=lambda x: x["score"], reverse=True)
        icons.sort(key=lambda x: x["score"], reverse=True)

        return {
            "archive_path": str(path.resolve()),
            "archive_filename": path.name,
            "archive_size_bytes": path.stat().st_size,
            "uncompressed_size_bytes": total_uncompressed_size,
            "total_files": len(members),
            "guessed_name": self.slugify(name),
            "guessed_display_name": display_name,
            "guessed_version": version,
            "has_wrapper_folder": has_wrapper,
            "wrapper_folder": single_root,
            "executables": executables,
            "icons": icons,
            "default_install_path": str(DEFAULT_OPT_DIR / self.slugify(name))
        }

    def _safe_extract_tar(self, tf: tarfile.TarFile, dest_dir: Path, strip_prefix: Optional[str] = None):
        """Extract tar members safely preventing path traversal"""
        dest_dir = dest_dir.resolve()
        for member in tf.getmembers():
            name = member.name
            if strip_prefix:
                if name == strip_prefix or name == strip_prefix + '/':
                    continue
                if name.startswith(strip_prefix + '/'):
                    name = name[len(strip_prefix) + 1:]
                else:
                    pass

            target_path = (dest_dir / name).resolve()
            try:
                target_path.relative_to(dest_dir)
            except ValueError:
                raise ArchiveError(f"Malicious member path traversal attempt: {member.name}")

            if member.isdir():
                target_path.mkdir(parents=True, exist_ok=True)
            elif member.isfile() or member.isreg():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with tf.extractfile(member) as src, open(target_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                try:
                    target_path.chmod(member.mode & 0o777)
                except Exception:
                    pass
            elif member.issym():
                target_path.parent.mkdir(parents=True, exist_ok=True)
                if target_path.is_symlink() or target_path.exists():
                    try:
                        target_path.unlink()
                    except Exception:
                        pass
                try:
                    os.symlink(member.linkname, str(target_path))
                except Exception:
                    pass

    def _safe_extract_zip(self, zf: zipfile.ZipFile, dest_dir: Path, strip_prefix: Optional[str] = None):
        """Extract zip members safely preventing path traversal"""
        dest_dir = dest_dir.resolve()
        for info in zf.infolist():
            name = info.filename
            if strip_prefix:
                if name == strip_prefix or name == strip_prefix + '/':
                    continue
                if name.startswith(strip_prefix + '/'):
                    name = name[len(strip_prefix) + 1:]

            if not name:
                continue

            target_path = (dest_dir / name).resolve()
            try:
                target_path.relative_to(dest_dir)
            except ValueError:
                raise ArchiveError(f"Malicious member path traversal attempt: {info.filename}")

            if info.is_dir():
                target_path.mkdir(parents=True, exist_ok=True)
            else:
                target_path.parent.mkdir(parents=True, exist_ok=True)
                with zf.open(info) as src, open(target_path, 'wb') as dst:
                    shutil.copyfileobj(src, dst)
                mode = info.external_attr >> 16
                if mode:
                    try:
                        target_path.chmod(mode & 0o777)
                    except Exception:
                        pass

    def extract_archive(self, archive_path: str, dest_dir: Path, flatten_wrapper: bool = True) -> Path:
        """Extract archive to destination directory with wrapper folder flattening"""
        path = Path(archive_path)
        dest_dir = Path(dest_dir).resolve()
        dest_dir.mkdir(parents=True, exist_ok=True)

        inspection = self.inspect_archive(str(path))
        strip_prefix = inspection["wrapper_folder"] if (flatten_wrapper and inspection["has_wrapper_folder"]) else None

        if zipfile.is_zipfile(str(path)):
            with zipfile.ZipFile(str(path), 'r') as zf:
                self._safe_extract_zip(zf, dest_dir, strip_prefix)
        else:
            with tarfile.open(str(path), 'r:*') as tf:
                self._safe_extract_tar(tf, dest_dir, strip_prefix)

        return dest_dir

    def scan_directory_candidates(self, directory: Path, app_name: str = "") -> Dict[str, List[Dict[str, Any]]]:
        """Scan an extracted or existing directory on disk to find executables and icons.

        Bolt Performance Optimization:
        - Avoid creating heavy `Path` objects in tight `os.walk` loops (~2x speedup).
        - Use direct string operations, cached set intersections for directory components,
          and a single `os.stat` call per file.
        """
        directory = Path(directory).resolve()
        dir_str = str(directory)
        if not directory.exists() or not directory.is_dir():
            return {"executables": [], "icons": []}

        executables = []
        icons = []
        ignored_exts = {
            '.txt', '.md', '.html', '.css', '.js', '.json', '.xml', '.png', '.jpg',
            '.jpeg', '.svg', '.so', '.a', '.la', '.o', '.h', '.c', '.cpp', '.hpp',
            '.pyc', '.pyo', '.mo', '.po', '.desktop', '.man', '.1', '.gz', '.zip',
            '.tar', '.xz', '.bz2', '.7z', '.bak', '.log', '.dat', '.pak', '.bin_blob',
            '.dylib', '.dll', '.tmp', '.lock', '.history', '.condarc', '.ini', '.cfg'
        }

        ignored_subdirs = {'include', 'man', 'doc', 'docs', 'locales', 'node_modules', '__pycache__', '.git', '.trash'}
        app_name_lower = app_name.lower() if app_name else ""

        for root, dirs, files in os.walk(dir_str):
            dirs[:] = [d for d in dirs if d not in ignored_subdirs and not d.startswith('.')]

            rel_root = os.path.relpath(root, dir_str)
            if rel_root == '.':
                rel_root = ''

            rel_root_parts = set(rel_root.split(os.sep)) if rel_root else set()

            for file in files:
                if file.startswith('.') or file.startswith('_'):
                    continue

                lower_name = file.lower()
                dot_idx = file.rfind('.')
                ext = file[dot_idx:].lower() if dot_idx != -1 else ''

                if '.so' in lower_name or (lower_name.startswith('lib') and (ext in {'.so', '.a', '.dylib', '.dll'} or '.so.' in lower_name)):
                    continue

                full_path_str = os.path.join(root, file)
                rel_path = os.path.join(rel_root, file) if rel_root else file
                lower_rel = rel_path.lower()

                if ext not in ignored_exts:
                    score = 0
                    is_exec_bit = False
                    is_elf = False
                    is_script = False
                    st_size = 0

                    try:
                        st = os.stat(full_path_str)
                        st_size = st.st_size
                        is_exec_bit = bool(st.st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH))

                        if st_size >= 4:
                            with open(full_path_str, 'rb') as f:
                                magic = f.read(4)
                                if magic.startswith(b'\x7fELF'):
                                    is_elf = True
                                elif magic.startswith(b'#!'):
                                    is_script = True
                    except Exception:
                        pass

                    if is_elf:
                        score += 80
                    elif is_script:
                        score += 50
                    elif is_exec_bit and not ext:
                        score += 30

                    if score > 0 or is_elf or is_script:
                        if app_name_lower and app_name_lower in lower_name:
                            score += 60
                        if rel_root in {'bin', 'usr/bin'}:
                            score += 35
                        elif not rel_root:
                            score += 25
                        if ext in {'.sh', '.bin', '.appimage'}:
                            score += 20

                        if rel_root_parts & {'lib', 'lib64', 'libexec', 'formats', 'resources', 'share'}:
                            score -= 40
                        if any(k in lower_name for k in {'crashpad', 'sandbox', 'helper', 'daemon', 'updater', 'install'}):
                            score -= 50

                        if score > 20:
                            executables.append({
                                "path": rel_path,
                                "full_path": full_path_str,
                                "score": score,
                                "is_elf": is_elf,
                                "is_script": is_script,
                                "size": st_size
                            })

                if ext in {'.png', '.svg', '.ico', '.xpm'}:
                    icon_score = 10
                    if any(k in lower_name for k in ['icon', 'logo', 'app']):
                        icon_score += 40
                    if any(k in lower_rel for k in ['icons', 'pixmaps', 'hicolor', 'scalable', 'resources/app']):
                        icon_score += 30
                    if app_name_lower and app_name_lower in lower_name:
                        icon_score += 45
                    if ext == '.svg':
                        icon_score += 20

                    try:
                        icon_size = os.path.getsize(full_path_str)
                    except Exception:
                        icon_size = 0

                    icons.append({
                        "path": rel_path,
                        "full_path": full_path_str,
                        "score": icon_score,
                        "size": icon_size
                    })

        executables.sort(key=lambda x: x["score"], reverse=True)
        icons.sort(key=lambda x: x["score"], reverse=True)
        return {"executables": executables, "icons": icons}

    def create_desktop_entry(
        self,
        name: str,
        display_name: str,
        exec_path: str,
        icon_path: Optional[str] = None,
        category: str = "Utility",
        terminal: bool = False,
        comment: Optional[str] = None
    ) -> str:
        """Create standard FreeDesktop .desktop file in ~/.local/share/applications"""
        slug = self.slugify(name)
        desktop_file = DEFAULT_DESKTOP_DIR / f"{slug}.desktop"

        categories_str = category if category.endswith(';') else f"{category};"

        content = [
            "[Desktop Entry]",
            "Type=Application",
            "Version=1.0",
            f"Name={display_name}",
            f"Comment={comment or display_name}",
            f"Exec=\"{exec_path}\" %U",
            f"Terminal={'true' if terminal else 'false'}",
            f"Categories={categories_str}",
            "StartupNotify=true"
        ]

        if icon_path and Path(icon_path).exists():
            content.append(f"Icon={icon_path}")
        else:
            content.append("Icon=application-x-executable")

        desktop_file.parent.mkdir(parents=True, exist_ok=True)
        with open(desktop_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(content) + '\n')

        try:
            desktop_file.chmod(0o755)
        except Exception:
            pass

        try:
            subprocess.run(["update-desktop-database", str(DEFAULT_DESKTOP_DIR)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass

        return str(desktop_file)

    def remove_desktop_entry(self, desktop_path: Optional[str]):
        """Remove desktop entry and update database"""
        if not desktop_path:
            return
        p = Path(desktop_path)
        if p.exists() and p.is_file():
            try:
                p.unlink()
                subprocess.run(["update-desktop-database", str(DEFAULT_DESKTOP_DIR)], check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            except Exception:
                pass

    def create_symlink(self, exec_path: str, symlink_name: str) -> str:
        """Create symlink in ~/.local/bin"""
        DEFAULT_BIN_DIR.mkdir(parents=True, exist_ok=True)
        slug = self.slugify(symlink_name)
        link_path = DEFAULT_BIN_DIR / slug

        if link_path.is_symlink() or link_path.exists():
            link_path.unlink()

        try:
            target = Path(exec_path)
            if target.exists():
                st = target.stat()
                target.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        os.symlink(exec_path, str(link_path))
        return str(link_path)

    def remove_symlink(self, symlink_path: Optional[str]):
        """Remove symlink from ~/.local/bin"""
        if not symlink_path:
            return
        p = Path(symlink_path)
        if p.is_symlink() or p.exists():
            try:
                p.unlink()
            except Exception:
                pass

    def install_app(
        self,
        archive_path: str,
        name: str,
        display_name: Optional[str] = None,
        version: Optional[str] = None,
        description: str = "",
        category: str = "Utility",
        install_path: Optional[str] = None,
        executable_rel_path: Optional[str] = None,
        icon_rel_path: Optional[str] = None,
        create_desktop: bool = True,
        create_bin_symlink: bool = True,
        flatten_wrapper: bool = True,
        terminal: bool = False,
        notes: str = ""
    ) -> Dict[str, Any]:
        """Perform full installation of an archive into ~/.local/opt/<app>"""
        slug = self.slugify(name)
        if not slug:
            raise ArchiveError("Invalid application name")

        target_dir = Path(install_path) if install_path else (DEFAULT_OPT_DIR / slug)
        target_dir = target_dir.resolve()

        if target_dir.exists() and any(target_dir.iterdir()):
            raise ArchiveError(f"Install directory already exists and is not empty: {target_dir}")

        self.extract_archive(archive_path, target_dir, flatten_wrapper=flatten_wrapper)

        if executable_rel_path:
            exec_full = (target_dir / executable_rel_path).resolve()
        else:
            candidates = self.scan_directory_candidates(target_dir, slug)
            if not candidates["executables"]:
                raise ArchiveError(f"No executable found in extracted archive. Please specify executable path.")
            exec_full = Path(candidates["executables"][0]["full_path"])

        if not exec_full.exists():
            raise ArchiveError(f"Specified executable does not exist: {exec_full}")

        try:
            st = exec_full.stat()
            exec_full.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        icon_full_str = None
        if icon_rel_path:
            cand_icon = (target_dir / icon_rel_path).resolve()
            if cand_icon.exists():
                icon_full_str = str(cand_icon)
        else:
            candidates = self.scan_directory_candidates(target_dir, slug)
            if candidates["icons"]:
                icon_full_str = candidates["icons"][0]["full_path"]

        calc_size = sum(f.stat().st_size for f in target_dir.rglob('*') if f.is_file() and not f.is_symlink())

        disp_name = display_name or slug.replace('-', ' ').title()
        ver = version or "1.0.0"

        desktop_path = None
        if create_desktop:
            desktop_path = self.create_desktop_entry(
                name=slug,
                display_name=disp_name,
                exec_path=str(exec_full),
                icon_path=icon_full_str,
                category=category,
                terminal=terminal,
                comment=description
            )

        symlink_path = None
        if create_bin_symlink:
            symlink_path = self.create_symlink(str(exec_full), slug)

        app_data = {
            "name": slug,
            "display_name": disp_name,
            "version": ver,
            "description": description,
            "category": category,
            "install_path": str(target_dir),
            "executable_path": str(exec_full),
            "symlink_path": symlink_path,
            "desktop_entry_path": desktop_path,
            "icon_path": icon_full_str,
            "source_type": "tarball",
            "source_path": str(Path(archive_path).resolve()),
            "size_bytes": calc_size,
            "terminal": terminal,
            "notes": notes
        }

        app_id = self.db.add_app(app_data)
        return self.db.get_app(app_id)

    def register_existing_app(
        self,
        name: str,
        install_path: str,
        executable_path: str,
        display_name: Optional[str] = None,
        version: str = "1.0.0",
        description: str = "",
        category: str = "Utility",
        icon_path: Optional[str] = None,
        create_desktop: bool = False,
        create_bin_symlink: bool = False,
        terminal: bool = False,
        notes: str = ""
    ) -> Dict[str, Any]:
        """Register an application that was already installed or extracted on disk"""
        slug = self.slugify(name)
        target_dir = Path(install_path).resolve()
        exec_full = Path(executable_path).resolve()

        if not target_dir.exists():
            raise ArchiveError(f"Install directory does not exist: {target_dir}")
        if not exec_full.exists():
            raise ArchiveError(f"Executable does not exist: {exec_full}")

        try:
            st = exec_full.stat()
            exec_full.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        icon_full_str = str(Path(icon_path).resolve()) if icon_path and Path(icon_path).exists() else None
        if not icon_full_str:
            candidates = self.scan_directory_candidates(target_dir, slug)
            if candidates["icons"]:
                icon_full_str = candidates["icons"][0]["full_path"]

        calc_size = 0
        try:
            calc_size = sum(f.stat().st_size for f in target_dir.rglob('*') if f.is_file() and not f.is_symlink())
        except Exception:
            pass

        disp_name = display_name or slug.replace('-', ' ').title()

        desktop_path = None
        if create_desktop:
            desktop_path = self.create_desktop_entry(
                name=slug,
                display_name=disp_name,
                exec_path=str(exec_full),
                icon_path=icon_full_str,
                category=category,
                terminal=terminal,
                comment=description
            )

        symlink_path = None
        if create_bin_symlink:
            symlink_path = self.create_symlink(str(exec_full), slug)

        app_data = {
            "name": slug,
            "display_name": disp_name,
            "version": version,
            "description": description,
            "category": category,
            "install_path": str(target_dir),
            "executable_path": str(exec_full),
            "symlink_path": symlink_path,
            "desktop_entry_path": desktop_path,
            "icon_path": icon_full_str,
            "source_type": "registered",
            "source_path": str(target_dir),
            "size_bytes": calc_size,
            "terminal": terminal,
            "notes": notes
        }

        app_id = self.db.add_app(app_data)
        return self.db.get_app(app_id)

    def update_app(
        self,
        app_id: int,
        archive_path: str,
        new_version: Optional[str] = None,
        flatten_wrapper: bool = True,
        executable_rel_path: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update an existing app with a new archive using atomic directory replacement"""
        app = self.db.get_app(app_id)
        if not app:
            raise ArchiveError(f"App with ID {app_id} not found")

        install_path = Path(app["install_path"]).resolve()
        parent_dir = install_path.parent
        backup_dir = parent_dir / f"{install_path.name}.bak_upgrade"
        staging_dir = parent_dir / f"{install_path.name}.stg_upgrade"

        if staging_dir.exists():
            shutil.rmtree(staging_dir, ignore_errors=True)
        if backup_dir.exists():
            shutil.rmtree(backup_dir, ignore_errors=True)

        try:
            self.extract_archive(archive_path, staging_dir, flatten_wrapper=flatten_wrapper)

            new_exec_path = None
            if executable_rel_path:
                cand = (staging_dir / executable_rel_path).resolve()
                if cand.exists():
                    new_exec_path = cand

            if not new_exec_path:
                try:
                    old_rel = Path(app["executable_path"]).relative_to(install_path)
                    cand = (staging_dir / old_rel).resolve()
                    if cand.exists():
                        new_exec_path = cand
                except Exception:
                    pass

            if not new_exec_path:
                candidates = self.scan_directory_candidates(staging_dir, app["name"])
                if candidates["executables"]:
                    new_exec_path = Path(candidates["executables"][0]["full_path"])

            if not new_exec_path or not new_exec_path.exists():
                raise ArchiveError("Could not locate executable in the new archive version.")

            st = new_exec_path.stat()
            new_exec_path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)

            rel_exec = new_exec_path.relative_to(staging_dir)
            final_exec_path = install_path / rel_exec

            cand_icons = self.scan_directory_candidates(staging_dir, app["name"])
            new_icon_path = app["icon_path"]
            if cand_icons["icons"]:
                new_icon_rel = Path(cand_icons["icons"][0]["full_path"]).relative_to(staging_dir)
                new_icon_path = str(install_path / new_icon_rel)

            if install_path.exists():
                self.run_elevated_mv(install_path, backup_dir)

            self.run_elevated_mv(staging_dir, install_path)

            if backup_dir.exists():
                self.run_elevated_rm(backup_dir)

        except Exception as e:
            if staging_dir.exists():
                self.run_elevated_rm(staging_dir)
            if backup_dir.exists() and not install_path.exists():
                self.run_elevated_mv(backup_dir, install_path)
            raise ArchiveError(f"Upgrade failed, restored previous state: {e}")

        desktop_entry_path = app["desktop_entry_path"]
        if desktop_entry_path and Path(desktop_entry_path).exists():
            desktop_entry_path = self.create_desktop_entry(
                name=app["name"],
                display_name=app["display_name"],
                exec_path=str(final_exec_path),
                icon_path=new_icon_path,
                category=app.get("category", "Utility"),
                terminal=bool(app.get("terminal")),
                comment=app.get("description", "")
            )

        symlink_path = app["symlink_path"]
        if symlink_path:
            symlink_path = self.create_symlink(str(final_exec_path), app["name"])

        calc_size = 0
        try:
            calc_size = sum(f.stat().st_size for f in install_path.rglob('*') if f.is_file() and not f.is_symlink())
        except Exception:
            pass

        ver = new_version
        if not ver:
            _, g_ver, _ = self.guess_name_and_version(Path(archive_path).name)
            ver = g_ver or app["version"]

        self.db.update_app(app_id, {
            "version": ver,
            "executable_path": str(final_exec_path),
            "desktop_entry_path": desktop_entry_path,
            "symlink_path": symlink_path,
            "icon_path": new_icon_path,
            "size_bytes": calc_size,
            "source_path": str(Path(archive_path).resolve())
        })

        return self.db.get_app(app_id)

    def uninstall_app(
        self,
        app_id: int,
        delete_files: bool = True,
        delete_desktop: bool = True,
        delete_symlink: bool = True
    ) -> Dict[str, Any]:
        """Uninstall an app: optionally removes files, desktop shortcut, symlink, and DB record"""
        app = self.db.get_app(app_id)
        if not app:
            raise ArchiveError(f"App with ID {app_id} not found")

        removed_items = []
        bytes_freed = app.get("size_bytes", 0)

        if delete_files:
            install_path = Path(app["install_path"])
            if install_path.exists():
                try:
                    self.run_elevated_rm(install_path)
                    removed_items.append(f"Directory: {install_path}")
                except Exception as e:
                    raise ArchiveError(f"Failed to delete install directory: {e}")

        if delete_desktop and app.get("desktop_entry_path"):
            self.remove_desktop_entry(app["desktop_entry_path"])
            removed_items.append(f"Desktop shortcut: {app['desktop_entry_path']}")

        if delete_symlink and app.get("symlink_path"):
            self.remove_symlink(app["symlink_path"])
            removed_items.append(f"Symlink: {app['symlink_path']}")

        self.db.delete_app(app_id)

        return {
            "success": True,
            "app_name": app["name"],
            "removed_items": removed_items,
            "bytes_freed": bytes_freed
        }

    def launch_app(self, app_id: int) -> bool:
        """Launch the application binary in a detached background process"""
        app = self.db.get_app(app_id)
        if not app:
            raise ArchiveError(f"App with ID {app_id} not found")

        exec_path = Path(app["executable_path"])
        if not exec_path.exists():
            raise ArchiveError(f"Executable not found at: {exec_path}")

        try:
            st = exec_path.stat()
            exec_path.chmod(st.st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        working_dir = Path(app["install_path"])
        if not working_dir.exists():
            working_dir = exec_path.parent

        if app.get("terminal"):
            cmd = ["x-terminal-emulator", "-e", str(exec_path)]
            try:
                subprocess.Popen(cmd, cwd=str(working_dir), start_new_session=True)
                return True
            except Exception:
                pass

        subprocess.Popen([str(exec_path)], cwd=str(working_dir), start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True

    def open_folder(self, app_id: int) -> bool:
        """Open the application install folder with system file manager"""
        app = self.db.get_app(app_id)
        if not app:
            raise ArchiveError(f"App with ID {app_id} not found")

        path = Path(app["install_path"])
        if not path.exists():
            raise ArchiveError(f"Directory not found: {path}")

        subprocess.Popen(["xdg-open", str(path)], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
