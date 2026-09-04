#!/usr/bin/env python3
"""
Clinux - Linux Cleaner & Portable App Manager
"""

import sys
import time
import socket
import argparse
import webbrowser
import threading
import subprocess
import urllib.request
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from targz_manager.db import Database
from targz_manager.installer import (
    Installer,
    DEFAULT_OPT_DIR,
    DEFAULT_BIN_DIR,
    DEFAULT_DESKTOP_DIR
)
from targz_manager.server import create_server


def find_free_port(start_port: int = 8421) -> int:
    """Find available port starting from start_port"""
    port = start_port
    while port < start_port + 100:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            res = sock.connect_ex(('127.0.0.1', port))
            if res != 0:
                return port
            port += 1
    return start_port


def check_server_running(host: str, port: int) -> bool:
    """Check if Clinux is already active on host:port"""
    try:
        url = f"http://{host}:{port}/api/system-info"
        req = urllib.request.Request(url, headers={"User-Agent": "ClinuxLauncher"})
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def open_browser_tab(url: str):
    """Open URL using xdg-open directly or Python webbrowser as fallback."""
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        webbrowser.open(url)


def install_desktop_shortcut_for_manager():
    """Install .desktop file for Clinux into ~/.local/share/applications"""
    script_path = Path(__file__).resolve()
    icon_path = script_path.parent / "targz_manager" / "static" / "icon.png"
    desktop_file = DEFAULT_DESKTOP_DIR / "clinux.desktop"

    content = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=Clinux",
        "GenericName=Linux Cleaner & Portable App Manager",
        "Comment=Clean system caches, purge package manager junk, and manage portable Linux applications",
        f"Exec=python3 \"{script_path}\"",
        f"Path={script_path.parent}",
        f"Icon={icon_path}",
        "Terminal=false",
        "Categories=System;Utility;PackageManager;Settings;",
        "StartupNotify=false"
    ]

    DEFAULT_DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
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

    print(f"✓ Installed Clinux desktop shortcut to: {desktop_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Clinux - Linux Cleaner & Portable App Manager"
    )

    parser.add_argument("--port", "-p", type=int, default=None, help="Port to bind server to (default: 8421)")
    parser.add_argument("--host", "-H", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    parser.add_argument("--keep-alive", action="store_true", help="Keep server running even after all browser tabs are closed")
    parser.add_argument("--db", type=str, default=None, help="Custom SQLite database file path")
    parser.add_argument("--install-desktop-entry", action="store_true", help="Install desktop shortcut for Clinux")

    args = parser.parse_args()

    if args.install_desktop_entry:
        install_desktop_shortcut_for_manager()
        return

    db_path = Path(args.db) if args.db else None
    db = Database(db_path)
    installer = Installer(db)

    target_port = args.port or 8421
    host = args.host
    url = f"http://{host}:{target_port}/"

    if check_server_running(host, target_port):
        print(f"✓ Clinux is already running at {url}. Opening browser tab...")
        if not args.no_browser:
            open_browser_tab(url)
        return

    port = args.port or find_free_port(target_port)
    url = f"http://{host}:{port}/"

    auto_shutdown = not args.keep_alive
    server = create_server(host=host, port=port, installer=installer, auto_shutdown=auto_shutdown)

    print("\n" + "=" * 65)
    print("  📦  Clinux, Linux Cleaner & Portable App Manager")
    print("=" * 65)
    print(f"  • Web UI URL:       \033[1;36m{url}\033[0m")
    print(f"  • Auto-Close:       {'Enabled (exits when tab is closed)' if auto_shutdown else 'Disabled (--keep-alive)'}")
    print(f"  • Database:         {installer.db.db_path}")
    print(f"  • Apps Directory:   {DEFAULT_OPT_DIR}")
    print(f"  • PATH Symlinks:    {DEFAULT_BIN_DIR}")
    print(f"  • Desktop Menus:    {DEFAULT_DESKTOP_DIR}")
    print("=" * 65)
    print("  Press \033[1;33mCtrl+C\033[0m anytime to stop the server.\n")

    if not args.no_browser:
        def open_browser():
            time.sleep(0.35)
            open_browser_tab(url)
        threading.Thread(target=open_browser, daemon=True).start()

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Clinux server... Goodbye!")
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
