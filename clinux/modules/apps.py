"""
Apps module for Clinux.
Wraps Database, Installer, and SystemScanner.
"""

from typing import Any, Dict, List, Optional
from clinux.modules.base import BaseModule
from targz_manager.db import Database
from targz_manager.installer import Installer
from targz_manager.scanner import SystemScanner


class AppsModule(BaseModule):
    id = "apps"
    name = "Apps"
    description = "Portable Linux application manager for tarballs and binaries."

    def __init__(self, db: Optional[Database] = None, installer: Optional[Installer] = None):
        self.db = db or Database()
        self.installer = installer or Installer(self.db)
        self.scanner = SystemScanner(self.db, self.installer)

    def scan(self, **kwargs) -> Dict[str, Any]:
        apps = self.db.list_apps()
        unmanaged = self.scanner.discover_unmanaged_apps()
        return {
            "installed_apps": apps,
            "unmanaged_apps": unmanaged,
            "total_installed": len(apps),
            "total_unmanaged": len(unmanaged),
        }

    def actions(self) -> List[Dict[str, Any]]:
        return [
            {"id": "list", "description": "List all installed applications"},
            {"id": "install", "description": "Install application from tarball archive"},
            {"id": "remove", "description": "Remove application"},
            {"id": "update", "description": "Update application with new archive"},
            {"id": "import_discovered", "description": "Import discovered unmanaged applications"},
        ]

    def run_action(self, action_name: str, **kwargs) -> Dict[str, Any]:
        if action_name == "list":
            return {"apps": self.db.list_apps()}
        elif action_name == "install":
            archive_path = kwargs.get("archive_path")
            if not archive_path:
                raise ValueError("archive_path is required for install action")
            app = self.installer.install_app(
                archive_path=archive_path,
                name=kwargs.get("name"),
                display_name=kwargs.get("display_name"),
                version=kwargs.get("version"),
                category=kwargs.get("category", "Utility"),
                install_path=kwargs.get("install_path"),
                create_desktop=kwargs.get("create_desktop", True),
                create_bin_symlink=kwargs.get("create_bin_symlink", True),
            )
            return {"app": app}
        elif action_name == "remove":
            app_id = kwargs.get("app_id")
            if not app_id:
                raise ValueError("app_id is required for remove action")
            res = self.installer.uninstall_app(
                app_id=app_id,
                delete_files=kwargs.get("delete_files", True),
                delete_desktop=kwargs.get("delete_desktop", True),
                delete_symlink=kwargs.get("delete_symlink", True),
            )
            return res
        elif action_name == "import_discovered":
            discovered = self.scanner.discover_unmanaged_apps()
            imported = []
            for d in discovered:
                try:
                    if d.get("is_tarball_archive") and d.get("archive_path"):
                        app = self.installer.install_app(
                            archive_path=d["archive_path"],
                            name=d["name"],
                            display_name=d["display_name"],
                            version=d["version"],
                        )
                    else:
                        app = self.installer.register_existing_app(
                            name=d["name"],
                            install_path=d["install_path"],
                            executable_path=d["executable_path"],
                            display_name=d["display_name"],
                            version=d.get("version", "1.0.0"),
                        )
                    imported.append(app)
                except Exception as e:
                    pass
            return {"imported": imported, "count": len(imported)}

        raise NotImplementedError(f"Action '{action_name}' is not supported.")
