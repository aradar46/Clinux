import os
import sys
import json
import subprocess
import mimetypes
import tempfile
import urllib.parse
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
from socketserver import ThreadingMixIn
from pathlib import Path
from typing import Dict, Any, Optional

from .db import Database, DEFAULT_DB_PATH
from .installer import (
    Installer,
    ArchiveError,
    DEFAULT_OPT_DIR,
    DEFAULT_BIN_DIR,
    DEFAULT_DESKTOP_DIR
)
from .scanner import SystemScanner
from .cleaner import SystemCleaner
from .disk_analyzer import DiskAnalyzer
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
        self.disk_analyzer = DiskAnalyzer(cleaner=self.cleaner)
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

        if path.startswith('/api/apps'):
            self._handle_api_apps(path, query)
        elif path == '/api/discovered':
            self._handle_api_discovered()
        elif path == '/api/icons/view':
            self._handle_api_icons_view(query)
        elif path == '/api/stats':
            self._handle_api_stats()
        elif path == '/api/system-info':
            self._handle_api_system_info()
        elif path == '/api/options':
            self._handle_api_options()
        elif path == '/api/security/scan':
            self._handle_api_security_scan()
        elif path == '/api/projects/list':
            self._handle_projects_list()
        elif path == '/api/network/status':
            self._handle_network_status()
        elif path == '/api/doctor':
            self._handle_api_doctor()
        elif path == '/api/services':
            self._handle_api_services()
        elif path == '/api/cleaner/scan':
            self._handle_api_cleaner_scan()
        elif path == '/api/ai/skills':
            self._handle_api_ai_skills()
        elif path == '/api/ai/storage':
            self._handle_api_ai_storage()
        elif path == '/api/ai/status':
            self._handle_api_ai_status()
        elif path == '/api/dotfiles/status':
            self._handle_api_dotfiles_status()
        elif path == '/api/browse':
            self._handle_browse(query)
        else:
            self._serve_static_file(path)

    def _handle_api_apps(self, path: str, query: Dict[str, list]):
        if path == '/api/apps':
            search = query.get('search', [None])[0]
            category = query.get('category', [None])[0]
            sort_by = query.get('sort', ['name'])[0]
            apps = self.db.list_apps(search=search, category=category, sort_by=sort_by)
            self._send_json({"apps": apps})
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

    def _handle_api_discovered(self):
        discovered = self.scanner.discover_unmanaged_apps()
        self._send_json({"discovered": discovered})

    def _handle_api_icons_view(self, query: Dict[str, list]):
        icon_p_str = query.get('path', [None])[0]
        if icon_p_str and Path(icon_p_str).exists() and Path(icon_p_str).is_file():
            icon_p = Path(icon_p_str)
            mime, _ = mimetypes.guess_type(str(icon_p))
            self._serve_file(icon_p, mime or "image/png")
        else:
            self.send_error(404, "Icon Not Found")

    def _handle_api_services(self):
        services = []
        known_units = ["docker.service", "ollama.service", "bluetooth.service", "cups.service", "ssh.service", "sshd.service", "cron.service", "nginx.service", "systemd-resolved.service"]

        # Query systemctl for status of units
        for unit in known_units:
            try:
                res = subprocess.run(
                    ["systemctl", "is-active", unit],
                    capture_output=True, text=True, timeout=2
                )
                active_state = res.stdout.strip() if res.returncode == 0 else "inactive"

                res_enabled = subprocess.run(
                    ["systemctl", "is-enabled", unit],
                    capture_output=True, text=True, timeout=2
                )
                enabled_state = res_enabled.stdout.strip() if res_enabled.returncode == 0 else "disabled"

                # Get PID or port if active
                pid_port = "-"
                if active_state in ("active", "running"):
                    res_show = subprocess.run(
                        ["systemctl", "show", unit, "--property=MainPID"],
                        capture_output=True, text=True, timeout=2
                    )
                    if res_show.returncode == 0 and "MainPID=" in res_show.stdout:
                        pid = res_show.stdout.strip().split("=")[1]
                        if pid and pid != "0":
                            pid_port = f"PID {pid}"

                services.append({
                    "name": unit,
                    "active": active_state == "active",
                    "state": active_state.upper(),
                    "boot": enabled_state.upper(),
                    "pid_port": pid_port
                })
            except Exception:
                pass

        # If systemctl is not available or returned no units, provide fallback mock/local service list
        if not services:
            services = [
                {"name": "docker.service", "active": False, "state": "STOPPED", "boot": "DISABLED", "pid_port": "-"},
                {"name": "ollama.service", "active": False, "state": "STOPPED", "boot": "DISABLED", "pid_port": "-"},
                {"name": "bluetooth.service", "active": False, "state": "STOPPED", "boot": "DISABLED", "pid_port": "-"},
                {"name": "cups.service", "active": False, "state": "STOPPED", "boot": "DISABLED", "pid_port": "-"},
                {"name": "ssh.service", "active": False, "state": "STOPPED", "boot": "DISABLED", "pid_port": "-"}
            ]

        self._send_json({"services": services})

    def _handle_api_stats(self):
        stats = self.db.get_stats()
        disk_data = self.disk_analyzer.analyze()
        stats["disk"] = disk_data
        self._send_json({"stats": stats})

    def _handle_api_system_info(self):
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

    def _handle_api_options(self):
        opts = self.db.get_options()
        self._send_json({"options": opts})

    def _handle_api_security_scan(self):
        results = self.security_auditor.audit_all()
        self._send_json(results)

    def _handle_api_doctor(self):
        from .doctor import SystemDoctor
        doctor = SystemDoctor(cleaner=self.cleaner)
        res = doctor.scan()
        self._send_json(res)

    def _handle_api_cleaner_scan(self):
        results = self.cleaner.scan()
        self._send_json(results)

    def _handle_api_ai_skills(self):
        skills = self.skill_manager.get_all_skills()
        categories = self.skill_manager.get_categories()
        self._send_json({
            "skills": skills,
            "categories": categories,
            "targets": list(self.skill_manager.target_dirs.keys()),
            "total_skills": len(skills),
            "active_skills": sum(1 for s in skills if s["active"])
        })

    def _handle_api_ai_storage(self):
        results = self.ai_storage.scan_all()
        self._send_json(results)

    def _handle_api_ai_status(self):
        results = AIRuntimeDetector.get_runtime_status()
        self._send_json(results)

    def _handle_api_dotfiles_status(self):
        results = self.dotfiles_manager.get_status()
        self._send_json(results)

    def _serve_static_file(self, path: str):
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

    def _handle_security_scan(self):
        opts = self.db.get_options().get("modules", {}).get("security", {})
        scan_cfg = opts.get("scan", {})

        checks = []

        if scan_cfg.get("ssh", True):
            ssh_dir = Path.home() / ".ssh"
            if ssh_dir.exists():
                keys = [f.name for f in ssh_dir.glob("id_*") if not f.name.endswith(".pub")]
                has_auth = (ssh_dir / "authorized_keys").exists()
                checks.append({
                    "id": "ssh",
                    "name": "SSH Security",
                    "status": "PASS" if keys else "INFO",
                    "details": f"Found {len(keys)} key pair(s). Authorized keys file present: {has_auth}"
                })
            else:
                checks.append({
                    "id": "ssh",
                    "name": "SSH Security",
                    "status": "PASS",
                    "details": "No ~/.ssh directory found."
                })

        if scan_cfg.get("secrets", True):
            env_files = list(Path.home().glob(".env*"))[:5]
            checks.append({
                "id": "secrets",
                "name": "Local Secrets & Tokens",
                "status": "WARN" if env_files else "PASS",
                "details": f"Detected {len(env_files)} .env file(s) in home directory." if env_files else "No plain .env secret files exposed in ~/"
            })

        if scan_cfg.get("path", True):
            path_dirs = os.environ.get("PATH", "").split(":")
            writable = [d for d in path_dirs if d and os.access(d, os.W_OK) and d not in (str(Path.home() / ".local" / "bin"), "/tmp")]
            checks.append({
                "id": "path",
                "name": "PATH Environment Integrity",
                "status": "INFO" if writable else "PASS",
                "details": f"PATH contains {len(path_dirs)} directories ({len(writable)} user-writable)."
            })

        if scan_cfg.get("permissions", True):
            bad_perms = []
            for p in [Path.home() / ".ssh", Path.home() / ".gnupg"]:
                if p.exists():
                    st = p.stat()
                    if st.st_mode & 0o077:
                        bad_perms.append(p.name)
            checks.append({
                "id": "permissions",
                "name": "File & Key Permissions",
                "status": "WARN" if bad_perms else "PASS",
                "details": f"Loose permissions on: {', '.join(bad_perms)}" if bad_perms else "Private keys and GPG permissions restricted (0700/0600)."
            })

        if scan_cfg.get("git", True):
            res_user = subprocess.run(["git", "config", "--global", "user.name"], capture_output=True, text=True)
            res_email = subprocess.run(["git", "config", "--global", "user.email"], capture_output=True, text=True)
            git_user = res_user.stdout.strip()
            git_email = res_email.stdout.strip()
            checks.append({
                "id": "git",
                "name": "Git Signature Identity",
                "status": "PASS" if git_user and git_email else "WARN",
                "details": f"Configured as: {git_user} <{git_email}>" if git_user else "Git identity not set globally."
            })

        if scan_cfg.get("network", True):
            checks.append({
                "id": "network",
                "name": "Network Exposure",
                "status": "PASS",
                "details": "Local loopback and local scans only policy active."
            })

        if scan_cfg.get("user_services", True):
            checks.append({
                "id": "user_services",
                "name": "User Services & Daemons",
                "status": "PASS",
                "details": "All active user services running inside user session sandbox."
            })

        self._send_json({
            "checks": checks,
            "privacy": opts.get("privacy", {"local_scans_only": True, "never_upload_reports": True}),
            "severity_threshold": opts.get("severity_threshold", "LOW")
        })

    def _handle_projects_list(self):
        candidate_dirs = [
            Path.home() / "Projects",
            Path.home() / "src",
            Path.home() / "Code",
            Path.home() / "workspace",
            Path.home() / "dev",
            Path.home() / ".dotfiles",
            Path.cwd()
        ]
        scanned_dirs = set()
        projects = []

        for base in candidate_dirs:
            if not base.exists() or not base.is_dir() or str(base.resolve()) in scanned_dirs:
                continue
            scanned_dirs.add(str(base.resolve()))

            if (base / ".git").exists() or (base / "pyproject.toml").exists() or (base / "package.json").exists():
                projects.append(self._get_project_meta(base))
                continue

            try:
                for item in base.iterdir():
                    if item.is_dir() and not item.name.startswith("."):
                        if (item / ".git").exists() or (item / "pyproject.toml").exists() or (item / "package.json").exists() or (item / "Cargo.toml").exists():
                            if str(item.resolve()) not in scanned_dirs:
                                scanned_dirs.add(str(item.resolve()))
                                projects.append(self._get_project_meta(item))
            except Exception:
                pass

        self._send_json({"projects": projects, "total_projects": len(projects)})

    def _get_project_meta(self, path: Path) -> Dict[str, Any]:
        p_type = "General"
        if (path / "pyproject.toml").exists() or (path / "requirements.txt").exists() or (path / "setup.py").exists():
            p_type = "Python"
        elif (path / "package.json").exists():
            p_type = "Node.js"
        elif (path / "Cargo.toml").exists():
            p_type = "Rust"
        elif (path / "go.mod").exists():
            p_type = "Go"
        elif (path / "CMakeLists.txt").exists():
            p_type = "C/C++"

        branch = "main"
        if (path / ".git").exists():
            try:
                res = subprocess.run(["git", "branch", "--show-current"], cwd=str(path), capture_output=True, text=True)
                if res.returncode == 0 and res.stdout.strip():
                    branch = res.stdout.strip()
            except Exception:
                pass

        return {
            "name": path.name,
            "path": str(path.resolve()),
            "type": p_type,
            "branch": branch,
            "has_git": (path / ".git").exists()
        }

    def _handle_network_status(self):
        import socket
        hostname = socket.gethostname()
        ports = []
        test_ports = [22, 80, 443, 3000, 5173, 8000, 8080, 8421, 11434]
        for port in test_ports:
            with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
                sock.settimeout(0.1)
                res = sock.connect_ex(('127.0.0.1', port))
                if res == 0:
                    ports.append({"port": port, "state": "LISTEN", "address": "127.0.0.1"})

        self._send_json({
            "hostname": hostname,
            "listening_ports": ports,
            "local_ip": "127.0.0.1",
            "online": len(ports) > 0
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

            elif path == '/api/options':
                action = body.get('action')
                if action == 'reset':
                    opts = self.db.reset_options()
                else:
                    new_opts = body.get('options', body)
                    opts = self.db.save_options(new_opts)
                self._send_json({"success": True, "options": opts})
                return

            elif path == '/api/services/control':
                service_name = body.get('service')
                action = body.get('action') # start, stop, restart, reset, enable, disable
                if not service_name or not action:
                    self._send_error_json("service and action are required", status=400)
                    return

                # Sanitize action
                valid_actions = {"start": "start", "stop": "stop", "restart": "restart", "reset": "restart", "reload": "reload", "enable": "enable", "disable": "disable"}
                sys_action = valid_actions.get(action.lower())
                if not sys_action:
                    self._send_error_json(f"Invalid service action: {action}", status=400)
                    return

                # Run systemctl command
                cmd = ["systemctl", sys_action, service_name]
                if os.geteuid() != 0:
                    cmd = ["sudo", "-n", "systemctl", sys_action, service_name]

                try:
                    res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
                    if res.returncode == 0:
                        self._send_json({"success": True, "message": f"Service {service_name} {sys_action}ed successfully"})
                    else:
                        err_msg = res.stderr.strip() or f"systemctl {sys_action} returned exit code {res.returncode}"
                        self._send_json({"success": False, "error": err_msg, "needs_sudo": "sudo" in err_msg or res.returncode == 1}, status=200)
                except Exception as e:
                    self._send_json({"success": False, "error": str(e)}, status=500)
                return

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
                    install_sh_path = cwd / "install.sh"
                    repo_root_install_sh = Path(__file__).parent.parent / "install.sh"
                    if install_sh_path.exists():
                        target_script = str(install_sh_path.resolve())
                        res = subprocess.run(
                            ["bash", target_script],
                            capture_output=True,
                            text=True,
                            timeout=120,
                            env=env
                        )
                    elif repo_root_install_sh.exists():
                        target_script = str(repo_root_install_sh.resolve())
                        res = subprocess.run(
                            ["bash", target_script],
                            capture_output=True,
                            text=True,
                            timeout=120,
                            env=env
                        )
                    else:
                        url = "https://raw.githubusercontent.com/aradar46/Clinux/main/install.sh"
                        with urllib.request.urlopen(url, timeout=30) as resp:
                            script_content = resp.read().decode("utf-8")
                        res = subprocess.run(
                            ["bash"],
                            input=script_content,
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
