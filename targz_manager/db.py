import os
import sqlite3
import datetime
from contextlib import contextmanager
from pathlib import Path
from typing import List, Dict, Optional, Any
from .utils import compute_directory_size

DEFAULT_DB_DIR = Path.home() / ".local" / "share" / "clinux"
DEFAULT_DB_PATH = DEFAULT_DB_DIR / "apps.db"
OLD_DB_PATH = Path.home() / ".local" / "share" / "targz-manager" / "apps.db"


class Database:
    def __init__(self, db_path: Optional[Path] = None):
        if db_path is None:
            DEFAULT_DB_DIR.mkdir(parents=True, exist_ok=True)
            if OLD_DB_PATH.exists() and not DEFAULT_DB_PATH.exists():
                try:
                    import shutil
                    shutil.copy2(OLD_DB_PATH, DEFAULT_DB_PATH)
                except Exception:
                    pass
            self.db_path = DEFAULT_DB_PATH
        else:
            self.db_path = Path(db_path)
            self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self.init_db()

    @contextmanager
    def _get_connection(self):
        conn = sqlite3.connect(str(self.db_path))
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    def init_db(self):
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS apps (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                display_name TEXT,
                version TEXT,
                description TEXT,
                category TEXT DEFAULT 'Utility',
                install_path TEXT NOT NULL UNIQUE,
                executable_path TEXT NOT NULL,
                symlink_path TEXT,
                desktop_entry_path TEXT,
                icon_path TEXT,
                source_type TEXT DEFAULT 'tarball',
                source_path TEXT,
                size_bytes INTEGER DEFAULT 0,
                terminal INTEGER DEFAULT 0,
                installed_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                notes TEXT,
                ignored INTEGER DEFAULT 0
            );
            """)
            try:
                cursor.execute("ALTER TABLE apps ADD COLUMN ignored INTEGER DEFAULT 0")
            except sqlite3.OperationalError:
                pass

            cursor.execute("""
            CREATE TABLE IF NOT EXISTS ignored_discoveries (
                key TEXT PRIMARY KEY,
                display_name TEXT,
                ignored_at TEXT NOT NULL
            );
            """)
            conn.commit()

    def add_app(self, app_data: Dict[str, Any]) -> int:
        now = datetime.datetime.now().isoformat()
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("""
            INSERT INTO apps (
                name, display_name, version, description, category,
                install_path, executable_path, symlink_path, desktop_entry_path,
                icon_path, source_type, source_path, size_bytes, terminal,
                installed_at, updated_at, notes
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                app_data["name"],
                app_data.get("display_name") or app_data["name"],
                app_data.get("version", "1.0.0"),
                app_data.get("description", ""),
                app_data.get("category", "Utility"),
                app_data["install_path"],
                app_data["executable_path"],
                app_data.get("symlink_path"),
                app_data.get("desktop_entry_path"),
                app_data.get("icon_path"),
                app_data.get("source_type", "tarball"),
                app_data.get("source_path"),
                app_data.get("size_bytes", 0),
                1 if app_data.get("terminal") else 0,
                app_data.get("installed_at", now),
                app_data.get("updated_at", now),
                app_data.get("notes", "")
            ))
            conn.commit()
            return cursor.lastrowid

    def get_app(self, app_id: int) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM apps WHERE id = ?", (app_id,))
            row = cursor.fetchone()
            if row:
                return self._enrich_app_data(dict(row))
            return None

    def get_app_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM apps WHERE name = ?", (name,))
            row = cursor.fetchone()
            if row:
                return self._enrich_app_data(dict(row))
            return None

    def get_app_by_install_path(self, install_path: str) -> Optional[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM apps WHERE install_path = ?", (install_path,))
            row = cursor.fetchone()
            if row:
                return self._enrich_app_data(dict(row))
            return None

    def list_apps(self, search: Optional[str] = None, category: Optional[str] = None, sort_by: str = "name") -> List[Dict[str, Any]]:
        query = "SELECT * FROM apps"
        params = []
        conditions = []

        if search:
            conditions.append("(name LIKE ? OR display_name LIKE ? OR description LIKE ?)")
            term = f"%{search}%"
            params.extend([term, term, term])

        if category and category.lower() != "all":
            conditions.append("category = ?")
            params.append(category)

        if conditions:
            query += " WHERE " + " AND ".join(conditions)

        if sort_by == "date_desc":
            query += " ORDER BY installed_at DESC"
        elif sort_by == "date_asc":
            query += " ORDER BY installed_at ASC"
        elif sort_by == "size_desc":
            query += " ORDER BY size_bytes DESC"
        elif sort_by == "size_asc":
            query += " ORDER BY size_bytes ASC"
        elif sort_by == "name_desc":
            query += " ORDER BY display_name DESC"
        else:
            query += " ORDER BY display_name ASC, name ASC"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, params)
            rows = cursor.fetchall()
            return [self._enrich_app_data(dict(row)) for row in rows]

    def update_app(self, app_id: int, updates: Dict[str, Any]) -> bool:
        if not updates:
            return False

        allowed_fields = {
            "display_name", "version", "description", "category",
            "install_path", "executable_path", "symlink_path", "desktop_entry_path",
            "icon_path", "source_type", "source_path", "size_bytes", "terminal",
            "updated_at", "notes", "ignored"
        }

        fields = []
        values = []
        for k, v in updates.items():
            if k in allowed_fields:
                fields.append(f"{k} = ?")
                if k in ("terminal", "ignored"):
                    values.append(1 if v else 0)
                else:
                    values.append(v)

        if not fields:
            return False

        if "updated_at" not in updates:
            fields.append("updated_at = ?")
            values.append(datetime.datetime.now().isoformat())

        values.append(app_id)
        query = f"UPDATE apps SET {', '.join(fields)} WHERE id = ?"

        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(query, values)
            conn.commit()
            return cursor.rowcount > 0

    def delete_app(self, app_id: int) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM apps WHERE id = ?", (app_id,))
            conn.commit()
            return cursor.rowcount > 0

    def ignore_discovery(self, key: str, display_name: str = "") -> None:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT OR REPLACE INTO ignored_discoveries (key, display_name, ignored_at) VALUES (?, ?, ?)",
                (key, display_name, datetime.datetime.now().isoformat())
            )
            conn.commit()

    def unignore_discovery(self, key: str) -> bool:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("DELETE FROM ignored_discoveries WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0

    def list_ignored_discoveries(self) -> List[Dict[str, Any]]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM ignored_discoveries ORDER BY ignored_at DESC")
            return [dict(row) for row in cursor.fetchall()]

    def get_stats(self) -> Dict[str, Any]:
        with self._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*), COALESCE(SUM(size_bytes), 0) FROM apps")
            total_apps, total_size = cursor.fetchone()

            cursor.execute("SELECT category, COUNT(*) FROM apps GROUP BY category")
            categories = dict(cursor.fetchall())

            cursor.execute("SELECT COUNT(*) FROM apps WHERE desktop_entry_path IS NOT NULL AND desktop_entry_path != ''")
            desktop_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM apps WHERE symlink_path IS NOT NULL AND symlink_path != ''")
            symlink_count = cursor.fetchone()[0]

            return {
                "total_apps": total_apps,
                "total_size_bytes": total_size,
                "total_size_formatted": self.format_size(total_size),
                "categories": categories,
                "desktop_count": desktop_count,
                "symlink_count": symlink_count
            }

    @staticmethod
    def format_size(bytes_val: int) -> str:
        if not bytes_val or bytes_val <= 0:
            return "0 B"
        units = ["B", "KB", "MB", "GB", "TB"]
        size = float(bytes_val)
        unit_idx = 0
        while size >= 1024.0 and unit_idx < len(units) - 1:
            size /= 1024.0
            unit_idx += 1
        return f"{size:.1f} {units[unit_idx]}" if unit_idx > 0 else f"{int(size)} B"

    def _enrich_app_data(self, data: Dict[str, Any]) -> Dict[str, Any]:
        """Verify file existence and compute health status"""
        install_path = Path(data.get("install_path", ""))
        exec_path = Path(data.get("executable_path", ""))
        symlink_path = Path(data["symlink_path"]) if data.get("symlink_path") else None
        desktop_path = Path(data["desktop_entry_path"]) if data.get("desktop_entry_path") else None
        icon_path = Path(data["icon_path"]) if data.get("icon_path") else None

        install_exists = install_path.exists() and install_path.is_dir()
        exec_exists = exec_path.exists() and os.access(str(exec_path), os.X_OK)
        symlink_exists = symlink_path.exists() if symlink_path else False
        desktop_exists = desktop_path.exists() if desktop_path else False
        icon_exists = icon_path.exists() if icon_path else False

        current_size = data.get("size_bytes", 0)
        if install_exists:
            try:
                # Fast directory size calculation using os.scandir (avoiding slow Path.rglob)
                calc_size = compute_directory_size(install_path)
                if calc_size > 0:
                    current_size = calc_size
            except Exception:
                pass

        if not install_exists:
            status = "missing_directory"
            status_message = "Installation directory not found"
            status_color = "red"
        elif not exec_exists:
            status = "missing_executable"
            status_message = "Executable binary missing or not executable"
            status_color = "yellow"
        else:
            status = "healthy"
            status_message = "Installed and operational"
            status_color = "green"

        data["size_bytes"] = current_size
        data["size_formatted"] = self.format_size(current_size)
        data["install_exists"] = install_exists
        data["exec_exists"] = exec_exists
        data["symlink_exists"] = symlink_exists
        data["desktop_exists"] = desktop_exists
        data["icon_exists"] = icon_exists
        data["needs_sudo"] = not os.access(str(install_path), os.W_OK) if install_exists else False
        data["status"] = status
        data["status_message"] = status_message
        data["status_color"] = status_color
        return data
