import os
import sys
import json
import subprocess
import mimetypes
import tempfile
import urllib.parse
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import Dict, Any, Optional

from .db import Database
from .installer import (
    Installer,
    ArchiveError,
    DEFAULT_OPT_DIR,
    DEFAULT_BIN_DIR,
    DEFAULT_DESKTOP_DIR
)
from .scanner import SystemScanner
from .cleaner import SystemCleaner
from .ai_manager import SkillManager, AIStorageManager, AIRuntimeDetector
from .dotfiles_manager import DotfilesManager
from .security import SecurityAuditor

import time
import threading

STATIC_DIR = Path(__file__).parent / "static"


class ThreadedHTTPServer(ThreadingMixIn, HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        *args,
        auto_shutdown: bool = False,
        shutdown_timeout: float = 60.0,
        disconnect_grace: float = 8.0,
        **kwargs
    ):
        super().__init__(*args, **kwargs)
        self.start_time = time.time()
        self.last_heartbeat = time.time()
        self.first_request_received = False
        self.auto_shutdown = auto_shutdown
        self.shutdown_timeout = shutdown_timeout
        self.disconnect_grace = disconnect_grace
        self.running = True
        self.active_clients = set()
        self.disconnect_timestamp = None

        if self.auto_shutdown:
            self._start_watchdog()

    def record_heartbeat(self, client_id: str = "default"):
        self.first_request_received = True
        self.last_heartbeat = time.time()
        self.active_clients.add(client_id)
        # Any heartbeat cancels pending disconnect
        self.disconnect_timestamp = None

    def record_disconnect(self, client_id: str = "default"):
        self.active_clients.discard(client_id)
        if not self.active_clients:
            if self.disconnect_timestamp is None:
                self.disconnect_timestamp = time.time()

    def _start_watchdog(self):
        def watchdog():
            while self.running:
                time.sleep(1.0)
                now = time.time()
                if self.first_request_received:
                    if self.disconnect_timestamp is not None:
                        if now - self.disconnect_timestamp > self.disconnect_grace:
                            self.running = False
                            threading.Thread(target=self.shutdown, daemon=True).start()
                            break
                    elif now - self.last_heartbeat > self.shutdown_timeout:
                        self.running = False
                        threading.Thread(target=self.shutdown, daemon=True).start()
                        break
                else:
                    if now - self.start_time > 90.0:
                        self.running = False
                        threading.Thread(target=self.shutdown, daemon=True).start()
                        break

        t = threading.Thread(target=watchdog, daemon=True)
        t.start()


class AppRequestHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, installer: Optional[Installer] = None, **kwargs):
        self.installer = installer or Installer()
        self.db = self.installer.db
        self.scanner = SystemScanner(self.db, self.installer)
        self.cleaner = SystemCleaner()
        self.skill_manager = SkillManager()
        self.ai_storage = AIStorageManager()
        self.dotfiles_manager = DotfilesManager()
        self.security_auditor = SecurityAuditor()
        super().__init__(*args, **kwargs)

    def log_message(self, format, *args):
        sys.stderr.write(f"[{self.log_date_time_string()}] {self.command} {self.path} - {format % args}\n")

    def _is_origin_allowed(self) -> bool:
        """
        Prevent CSRF and cross-site attacks from external web pages.
        Requests with an Origin header are only permitted if they originate
        from localhost or 127.0.0.1.
        """
        origin = self.headers.get('Origin')
        if not origin:
            return True
        allowed_prefixes = (
            'http://127.0.0.1',
            'http://localhost',
            'http://[::1]',
            'https://127.0.0.1',
            'https://localhost'
        )
        return any(origin.startswith(prefix) for prefix in allowed_prefixes)

    def _send_json(self, data: Any, status: int = 200):
        body = json.dumps(data, indent=2).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        origin = self.headers.get('Origin')
        if origin and self._is_origin_allowed():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()
        self.wfile.write(body)

    def _send_error_json(self, message: str, status: int = 400, details: Any = None):
        self._send_json({"error": message, "details": details}, status=status)

    def _read_json_body(self) -> Dict[str, Any]:
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            return {}
        body = self.rfile.read(content_length)
        return json.loads(body.decode('utf-8'))

    def do_OPTIONS(self):
        if not self._is_origin_allowed():
            self.send_error(403, "Cross-origin request forbidden")
            return
        self.send_response(204)
        origin = self.headers.get('Origin')
        if origin and self._is_origin_allowed():
            self.send_header('Access-Control-Allow-Origin', origin)
            self.send_header('Access-Control-Allow-Methods', 'GET, POST, DELETE, OPTIONS')
            self.send_header('Access-Control-Allow-Headers', 'Content-Type')
        self.end_headers()

    def do_GET(self):
        if not self._is_origin_allowed():
            self.send_error(403, "Cross-origin request forbidden")
            return
        if hasattr(self.server, 'record_heartbeat'):
            self.server.record_heartbeat("page_get")

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path == '/api/apps':
            search = query.get('search', [None])[0]
            category = query.get('category', [None])[0]
            sort_by = query.get('sort', ['name'])[0]
            apps = self.db.list_apps(search=search, category=category, sort_by=sort_by)
            self._send_json({"apps": apps})
            return

        elif path.startswith('/api/apps/') and path.endswith('/icon'):
            try:
                app_id = int(path.split('/')[3])
                app = self.db.get_app(app_id)
                if app and app.get("icon_path") and Path(app["icon_path"]).exists():
                    icon_p = Path(app["icon_path"])
                    mime, _ = mimetypes.guess_type(str(icon_p))
                    self._serve_file(icon_p, mime or "image/png")
                else:
                    self.send_error(404, "Icon Not Found")
            except ValueError:
                self._send_error_json("Invalid app ID", status=400)
            return

        elif path.startswith('/api/apps/'):
            try:
                app_id = int(path.split('/')[3])
                app = self.db.get_app(app_id)
                if app:
                    self._send_json({"app": app})
                else:
                    self._send_error_json(f"App {app_id} not found", status=404)
            except ValueError:
                self._send_error_json("Invalid app ID", status=400)
            return

        elif path == '/api/discovered':
            discovered = self.scanner.discover_unmanaged_apps()
            self._send_json({"discovered": discovered})
            return

        elif path == '/api/icons/view':
            icon_p_str = query.get('path', [None])[0]
            if icon_p_str and Path(icon_p_str).exists() and Path(icon_p_str).is_file():
                icon_p = Path(icon_p_str)
                mime, _ = mimetypes.guess_type(str(icon_p))
                self._serve_file(icon_p, mime or "image/png")
            else:
                self.send_error(404, "Icon Not Found")
            return

        elif path == '/api/stats':
            stats = self.db.get_stats()
            self._send_json({"stats": stats})
            return

        elif path == '/api/system-info':
            path_env = os.environ.get("PATH", "").split(":")
            bin_in_path = str(DEFAULT_BIN_DIR) in path_env or str(DEFAULT_BIN_DIR.resolve()) in path_env
            self._send_json({
                "home": str(Path.home()),
                "opt_dir": str(DEFAULT_OPT_DIR),
                "bin_dir": str(DEFAULT_BIN_DIR),
                "desktop_dir": str(DEFAULT_DESKTOP_DIR),
                "db_path": str(self.db.db_path),
                "bin_in_path": bin_in_path,
                "user": os.environ.get("USER", "user")
            })
            return

        elif path == '/api/cleaner/scan':
            results = self.cleaner.scan()
            self._send_json(results)
            return

        elif path == '/api/ai/skills':
            skills = self.skill_manager.get_all_skills()
            categories = self.skill_manager.get_categories()
            self._send_json({
                "skills": skills,
                "categories": categories,
                "targets": list(self.skill_manager.target_dirs.keys()),
                "total_skills": len(skills),
                "active_skills": sum(1 for s in skills if s["active"])
            })
            return

        elif path == '/api/ai/storage':
            results = self.ai_storage.scan_all()
            self._send_json(results)
            return

        elif path == '/api/ai/status':
            results = AIRuntimeDetector.get_runtime_status()
            self._send_json(results)
            return

        elif path == '/api/dotfiles/status':
            results = self.dotfiles_manager.get_status()
            self._send_json(results)
            return

        elif path == '/api/security/scan':
            results = self.security_auditor.audit_all()
            self._send_json(results)
            return

        elif path == '/api/browse':
            self._handle_browse(query)
            return

        if path == '/' or path == '/index.html':
            self._serve_file(STATIC_DIR / "index.html", "text/html")
        else:
            rel_path = path.lstrip('/')
            if rel_path.startswith('static/'):
                rel_path = rel_path[len('static/'):]

            file_path = (STATIC_DIR / rel_path).resolve()
            try:
                file_path.relative_to(STATIC_DIR)
                if file_path.exists() and file_path.is_file():
                    mime, _ = mimetypes.guess_type(str(file_path))
                    self._serve_file(file_path, mime or "application/octet-stream")
                else:
                    self.send_error(404, "File Not Found")
            except ValueError:
                self.send_error(403, "Access Forbidden")

    def _serve_file(self, file_path: Path, content_type: str):
        try:
            with open(file_path, 'rb') as f:
                content = f.read()
            self.send_response(200)
            self.send_header('Content-Type', f'{content_type}; charset=utf-8' if 'text' in content_type or 'javascript' in content_type else content_type)
            self.send_header('Content-Length', str(len(content)))
            self.end_headers()
            self.wfile.write(content)
        except Exception as e:
            self.send_error(500, f"Error reading file: {e}")

    def _handle_browse(self, query: Dict[str, list]):
        raw_path = query.get('path', [str(Path.home())])[0]
        mode = query.get('mode', ['all'])[0]

        target = Path(raw_path).expanduser().resolve()
        if not target.exists():
            target = Path.home()

        if target.is_file():
            target = target.parent

        archive_exts = {'.tar.gz', '.tgz', '.tar.bz2', '.tbz2', '.tar.xz', '.txz', '.tar', '.zip'}

        show_hidden_val = query.get('show_hidden', ['1'])[0]
        show_hidden = show_hidden_val.lower() not in ('0', 'false', 'no')

        items = []
        try:
            for entry in sorted(target.iterdir(), key=lambda x: (not x.is_dir(), x.name.lower())):
                is_hidden = entry.name.startswith('.')
                if is_hidden and not show_hidden:
                    continue

                is_dir = entry.is_dir()
                is_archive = any(entry.name.lower().endswith(ext) for ext in archive_exts)
                is_exec = False

                if not is_dir:
                    try:
                        st = entry.stat()
                        is_exec = bool(st.st_mode & 0o111)
                    except Exception:
                        pass

                if mode == 'dir' and not is_dir:
                    continue
                elif mode == 'archive' and not (is_dir or is_archive):
                    continue
                elif mode == 'executable' and not (is_dir or is_exec or is_archive):
                    continue

                size = 0
                if not is_dir:
                    try:
                        size = entry.stat().st_size
                    except Exception:
                        pass

                items.append({
                    "name": entry.name,
                    "path": str(entry.resolve()),
                    "is_dir": is_dir,
                    "is_archive": is_archive,
                    "is_exec": is_exec,
                    "is_hidden": is_hidden,
                    "size_bytes": size,
                    "size_formatted": Database.format_size(size) if not is_dir else None
                })
        except PermissionError:
            pass

        quick_links = [
            {"name": "Home", "path": str(Path.home())},
            {"name": "Downloads", "path": str(Path.home() / "Downloads")},
            {"name": "Desktop", "path": str(Path.home() / "Desktop")},
            {"name": "Local Opt (~/.local/opt)", "path": str(DEFAULT_OPT_DIR)},
            {"name": "System Opt (/opt)", "path": "/opt"},
            {"name": "Current Dir", "path": str(Path.cwd())}
        ]
        quick_links = [ql for ql in quick_links if Path(ql["path"]).exists()]

        self._send_json({
            "current_path": str(target),
            "parent_path": str(target.parent) if target.parent != target else None,
            "home_path": str(Path.home()),
            "quick_links": quick_links,
            "items": items
        })

    def do_POST(self):
        if not self._is_origin_allowed():
            self.send_error(403, "Cross-origin request forbidden")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path == '/api/upload':
            self._handle_upload()
            return

        try:
            body = self._read_json_body()
        except Exception as e:
            self._send_error_json(f"Invalid JSON body: {e}", status=400)
            return

        try:
            if path == '/api/heartbeat':
                client_id = body.get('client_id', 'default') if isinstance(body, dict) else 'default'
                if hasattr(self.server, 'record_heartbeat'):
                    self.server.record_heartbeat(client_id)
                self._send_json({"status": "alive", "timestamp": time.time()})
                return

            elif path == '/api/shutdown':
                client_id = body.get('client_id', 'default') if isinstance(body, dict) else 'default'
                if hasattr(self.server, 'record_disconnect'):
                    self.server.record_disconnect(client_id)
                self._send_json({"status": "shutting_down"})
                return

            elif path == '/api/apps/inspect':
                archive_path = body.get('archive_path')
                if not archive_path:
                    self._send_error_json("archive_path is required")
                    return
                info = self.installer.inspect_archive(archive_path)
                self._send_json(info)

            elif path == '/api/apps/auto-resolve':
                dir_path = body.get('path')
                if not dir_path:
                    self._send_error_json("path is required")
                    return
                res = self.scanner.auto_resolve_directory(dir_path)
                self._send_json(res)

            elif path == '/api/discovered/add':
                if body.get('is_tarball_archive') and body.get('archive_path'):
                    insp = self.installer.inspect_archive(body['archive_path'])
                    app = self.installer.install_app(
                        archive_path=body['archive_path'],
                        name=body.get('name') or insp['guessed_name'],
                        display_name=body.get('display_name') or insp['guessed_display_name'],
                        version=body.get('version') or insp['guessed_version'],
                        category=body.get('category', 'Utility'),
                        install_path=body.get('install_path'),
                        create_desktop=body.get('create_desktop', True),
                        create_bin_symlink=body.get('create_bin_symlink', True)
                    )
                else:
                    app = self.installer.register_existing_app(
                        name=body['name'],
                        install_path=body['install_path'],
                        executable_path=body['executable_path'],
                        display_name=body.get('display_name'),
                        version=body.get('version', '1.0.0'),
                        category=body.get('category', 'Utility'),
                        icon_path=body.get('icon_path'),
                        create_desktop=body.get('create_desktop', True),
                        create_bin_symlink=body.get('create_bin_symlink', True),
                        terminal=body.get('terminal', False),
                        description=body.get('description', '')
                    )
                self._send_json({"success": True, "app": app})

            elif path == '/api/discovered/ignore':
                key = body.get('key')
                if not key:
                    self._send_error_json("key is required")
                    return
                self.db.ignore_discovery(key, body.get('display_name', ''))
                self._send_json({"success": True})

            elif path == '/api/discovered/unignore':
                key = body.get('key')
                if not key:
                    self._send_error_json("key is required")
                    return
                self.db.unignore_discovery(key)
                self._send_json({"success": True})

            elif path == '/api/cleaner/clean':
                target_ids = body.get('targets', [])
                sudo_password = body.get('password')
                res = self.cleaner.clean(target_ids, sudo_password=sudo_password)
                self._send_json(res)
                return

            elif path == '/api/ai/skills/toggle':
                category = body.get('category')
                key = body.get('key')
                active = body.get('active', True)
                targets = body.get('targets')

                if category:
                    res = self.skill_manager.toggle_category(category, active=active, targets=targets)
                elif key:
                    if active:
                        res = self.skill_manager.activate_skill(key, targets=targets)
                    else:
                        res = self.skill_manager.deactivate_skill(key, targets=targets)
                else:
                    self._send_error_json("Either 'key' or 'category' is required", status=400)
                    return
                self._send_json(res)
                return

            elif path == '/api/ai/storage/delete':
                model_id = body.get('model_id')
                if not model_id:
                    self._send_error_json("model_id is required", status=400)
                    return
                res = self.ai_storage.delete_model(model_id)
                self._send_json(res)
                return

            elif path == '/api/ai/storage/clean':
                workspace_id = body.get('workspace_id')
                if not workspace_id:
                    self._send_error_json("workspace_id is required", status=400)
                    return
                res = self.ai_storage.clean_workspace(workspace_id)
                self._send_json(res)
                return

            elif path == '/api/dotfiles/run':
                cmd_name = body.get('command')
                msg = body.get('message')
                pkg = body.get('package')
                if not cmd_name:
                    self._send_error_json("command is required", status=400)
                    return
                res = self.dotfiles_manager.run_command(cmd_name, message=msg, package=pkg)
                self._send_json(res)
                return

            elif path == '/api/security/export':
                fmt = body.get('format', 'text')
                filepath = body.get('filepath')
                scan_res = self.security_auditor.audit_all()
                out_path = self.security_auditor.export_report(scan_res, filepath=filepath, format_type=fmt)
                if fmt == "json":
                    content = json.dumps(scan_res, indent=2)
                else:
                    content = self.security_auditor.format_text_report(scan_res)
                self._send_json({
                    "success": True,
                    "filepath": out_path,
                    "filename": Path(out_path).name,
                    "content": content
                })
                return

            elif path == '/api/self-update':
                cmd = "curl -fsSL https://raw.githubusercontent.com/aradar46/Clinux/main/install.sh | bash"
                env = os.environ.copy()
                env["HOME"] = str(Path.home())
                env["PATH"] = os.environ.get("PATH", "/usr/local/bin:/usr/bin:/bin")

                cwd = Path.cwd()
                local_pull_out = ""
                if (cwd / ".git").exists() and (cwd / "targz_manager").exists():
                    try:
                        pull_res = subprocess.run(
                            ["git", "pull", "--ff-only"],
                            cwd=str(cwd),
                            capture_output=True,
                            text=True,
                            timeout=30
                        )
                        local_pull_out = (pull_res.stdout + pull_res.stderr).strip()
                    except Exception as e:
                        local_pull_out = f"Git pull notice: {e}"

                try:
                    res = subprocess.run(
                        cmd,
                        shell=True,
                        capture_output=True,
                        text=True,
                        timeout=120,
                        env=env
                    )
                    combined_output = "\n".join(filter(None, [local_pull_out, res.stdout, res.stderr])).strip()
                    self._send_json({
                        "success": res.returncode == 0,
                        "returncode": res.returncode,
                        "output": combined_output or "Update completed."
                    })
                except Exception as e:
                    self._send_json({
                        "success": False,
                        "error": str(e),
                        "output": local_pull_out
                    }, status=500)
                return

            elif path == '/api/apps/scan-directory':
                dir_path = body.get('dir_path')
                app_name = body.get('app_name', '')
                if not dir_path:
                    self._send_error_json("dir_path is required")
                    return
                candidates = self.installer.scan_directory_candidates(Path(dir_path), app_name)
                self._send_json(candidates)

            elif path == '/api/apps/install':
                app = self.installer.install_app(
                    archive_path=body["archive_path"],
                    name=body["name"],
                    display_name=body.get("display_name"),
                    version=body.get("version"),
                    description=body.get("description", ""),
                    category=body.get("category", "Utility"),
                    install_path=body.get("install_path"),
                    executable_rel_path=body.get("executable_rel_path"),
                    icon_rel_path=body.get("icon_rel_path"),
                    create_desktop=body.get("create_desktop", True),
                    create_bin_symlink=body.get("create_bin_symlink", True),
                    flatten_wrapper=body.get("flatten_wrapper", True),
                    terminal=body.get("terminal", False),
                    notes=body.get("notes", "")
                )
                self._send_json({"success": True, "app": app})

            elif path == '/api/apps/register':
                app = self.installer.register_existing_app(
                    name=body["name"],
                    install_path=body["install_path"],
                    executable_path=body["executable_path"],
                    display_name=body.get("display_name"),
                    version=body.get("version", "1.0.0"),
                    description=body.get("description", ""),
                    category=body.get("category", "Utility"),
                    icon_path=body.get("icon_path"),
                    create_desktop=body.get("create_desktop", False),
                    create_bin_symlink=body.get("create_bin_symlink", False),
                    terminal=body.get("terminal", False),
                    notes=body.get("notes", "")
                )
                self._send_json({"success": True, "app": app})

            elif path.startswith('/api/apps/') and path.endswith('/update'):
                app_id = int(path.split('/')[3])
                archive_path = body.get("archive_path")
                if not archive_path:
                    self._send_error_json("archive_path is required")
                    return
                app = self.installer.update_app(
                    app_id=app_id,
                    archive_path=archive_path,
                    new_version=body.get("version"),
                    flatten_wrapper=body.get("flatten_wrapper", True),
                    executable_rel_path=body.get("executable_rel_path")
                )
                self._send_json({"success": True, "app": app})

            elif path.startswith('/api/apps/') and path.endswith('/launch'):
                app_id = int(path.split('/')[3])
                self.installer.launch_app(app_id)
                self._send_json({"success": True, "message": "App launched successfully"})

            elif path.startswith('/api/apps/') and path.endswith('/open-folder'):
                app_id = int(path.split('/')[3])
                self.installer.open_folder(app_id)
                self._send_json({"success": True, "message": "Folder opened in file manager"})

            elif path.startswith('/api/apps/') and path.endswith('/toggle-shortcut'):
                app_id = int(path.split('/')[3])
                shortcut_type = body.get("type")
                enable = body.get("enable", True)
                app = self.db.get_app(app_id)
                if not app:
                    self._send_error_json("App not found", status=404)
                    return

                if shortcut_type == "desktop":
                    if enable:
                        new_path = self.installer.create_desktop_entry(
                            name=app["name"],
                            display_name=app["display_name"],
                            exec_path=app["executable_path"],
                            icon_path=app["icon_path"],
                            category=app["category"],
                            terminal=bool(app.get("terminal")),
                            comment=app.get("description", "")
                        )
                        self.db.update_app(app_id, {"desktop_entry_path": new_path})
                    else:
                        self.installer.remove_desktop_entry(app.get("desktop_entry_path"))
                        self.db.update_app(app_id, {"desktop_entry_path": None})

                elif shortcut_type == "symlink":
                    if enable:
                        new_link = self.installer.create_symlink(app["executable_path"], app["name"])
                        self.db.update_app(app_id, {"symlink_path": new_link})
                    else:
                        self.installer.remove_symlink(app.get("symlink_path"))
                        self.db.update_app(app_id, {"symlink_path": None})

                self._send_json({"success": True, "app": self.db.get_app(app_id)})

            elif path.startswith('/api/apps/') and path.endswith('/edit'):
                app_id = int(path.split('/')[3])
                updates = {k: v for k, v in body.items() if k in {
                    "display_name", "version", "description", "category",
                    "executable_path", "icon_path", "terminal", "notes", "ignored"
                }}
                self.db.update_app(app_id, updates)
                self._send_json({"success": True, "app": self.db.get_app(app_id)})

            else:
                self._send_error_json("Endpoint not found", status=404)

        except ArchiveError as e:
            self._send_error_json(str(e), status=400)
        except Exception as e:
            self._send_error_json(f"Internal server error: {e}", status=500)

    def _handle_upload(self):
        """Handle multipart file upload without third-party dependencies"""
        content_type = self.headers.get('Content-Type', '')
        if not content_type.startswith('multipart/form-data'):
            self._send_error_json("Expected multipart/form-data", status=400)
            return

        boundary = None
        for part in content_type.split(';'):
            part = part.strip()
            if part.startswith('boundary='):
                boundary = part[9:].strip('"').encode('latin1')
                break

        if not boundary:
            self._send_error_json("Missing boundary in form data", status=400)
            return

        content_length = int(self.headers.get('Content-Length', 0))
        if content_length <= 0:
            self._send_error_json("Empty upload", status=400)
            return

        raw_data = self.rfile.read(content_length)

        delimiter = b'--' + boundary
        parts = raw_data.split(delimiter)

        saved_file_path = None
        orig_filename = "uploaded_archive.tar.gz"

        for part in parts:
            if not part or part == b'--\r\n' or part == b'--':
                continue
            if b'\r\n\r\n' not in part:
                continue

            headers_bytes, content_bytes = part.split(b'\r\n\r\n', 1)
            if content_bytes.endswith(b'\r\n'):
                content_bytes = content_bytes[:-2]

            headers_str = headers_bytes.decode('latin1')
            if 'filename="' in headers_str:
                fn_match = re_match = None
                for line in headers_str.split('\r\n'):
                    if 'Content-Disposition' in line and 'filename=' in line:
                        fn_part = line.split('filename=')[1]
                        orig_filename = fn_part.strip('"; \r\n')
                        if orig_filename.startswith('"') and orig_filename.endswith('"'):
                            orig_filename = orig_filename[1:-1]
                        break

                temp_dir = Path(tempfile.gettempdir()) / "targz_uploads"
                temp_dir.mkdir(parents=True, exist_ok=True)
                clean_fn = Path(orig_filename).name
                dest_file = temp_dir / clean_fn

                with open(dest_file, 'wb') as f:
                    f.write(content_bytes)

                saved_file_path = str(dest_file.resolve())
                break

        if not saved_file_path:
            self._send_error_json("No file was received in upload", status=400)
            return

        try:
            inspection = self.installer.inspect_archive(saved_file_path)
            self._send_json({
                "success": True,
                "saved_path": saved_file_path,
                "filename": orig_filename,
                "inspection": inspection
            })
        except Exception as e:
            self._send_json({
                "success": True,
                "saved_path": saved_file_path,
                "filename": orig_filename,
                "inspection_error": str(e)
            })

    def do_DELETE(self):
        if not self._is_origin_allowed():
            self.send_error(403, "Cross-origin request forbidden")
            return

        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        if path.startswith('/api/apps/'):
            try:
                app_id = int(path.split('/')[3])
                delete_files = query.get('delete_files', ['true'])[0].lower() == 'true'
                delete_desktop = query.get('delete_desktop', ['true'])[0].lower() == 'true'
                delete_symlink = query.get('delete_symlink', ['true'])[0].lower() == 'true'

                result = self.installer.uninstall_app(
                    app_id=app_id,
                    delete_files=delete_files,
                    delete_desktop=delete_desktop,
                    delete_symlink=delete_symlink
                )
                self._send_json(result)
            except ArchiveError as e:
                self._send_error_json(str(e), status=400)
            except Exception as e:
                self._send_error_json(f"Error during uninstall: {e}", status=500)
        else:
            self._send_error_json("Invalid DELETE endpoint", status=404)


def create_server(
    host: str = "127.0.0.1",
    port: int = 8421,
    installer: Optional[Installer] = None,
    auto_shutdown: bool = False,
    shutdown_timeout: float = 60.0,
    disconnect_grace: float = 8.0,
) -> ThreadedHTTPServer:
    inst = installer or Installer()

    def handler_factory(*args, **kwargs):
        return AppRequestHandler(*args, installer=inst, **kwargs)

    server = ThreadedHTTPServer(
        (host, port),
        handler_factory,
        auto_shutdown=auto_shutdown,
        shutdown_timeout=shutdown_timeout,
        disconnect_grace=disconnect_grace,
    )
    return server
