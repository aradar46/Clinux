#!/usr/bin/env python3
"""
TarGz App Manager - Linux Portable App & Tarball Package Manager
Zero-dependency package and application manager for manually extracted tarballs.
"""

import os
import sys
import time
import socket
import argparse
import webbrowser
import threading
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.resolve()))

from targz_manager.db import Database, DEFAULT_DB_PATH
from targz_manager.installer import (
    Installer,
    ArchiveError,
    DEFAULT_OPT_DIR,
    DEFAULT_BIN_DIR,
    DEFAULT_DESKTOP_DIR
)
from targz_manager.server import create_server
from targz_manager.cleaner import SystemCleaner


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


def print_cli_table(apps):
    if not apps:
        print("\nNo applications are currently managed by TarGz Manager.")
        print("Run with the GUI or use: python3 app.py install <archive.tar.gz>\n")
        return

    print("\n" + "=" * 80)
    print(f"{'ID':<4} {'NAME':<20} {'VERSION':<10} {'SIZE':<10} {'STATUS':<12} {'EXEC PATH'}")
    print("-" * 80)
    for app in apps:
        status = "✓ OK" if app.get("status") == "healthy" else "⚠ Issue"
        exec_p = app.get("executable_path", "")
        if len(exec_p) > 28:
            exec_p = "..." + exec_p[-25:]
        print(f"{app['id']:<4} {app['display_name'][:18]:<20} {app['version'][:8]:<10} {app['size_formatted']:<10} {status:<12} {exec_p}")
    print("=" * 80 + "\n")


def main():
    parser = argparse.ArgumentParser(
        description="Clinux - Linux Cleaner & Portable App Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 app.py                         # Launch GUI web server and open browser
  python3 app.py --port 8080             # Run on custom port
  python3 app.py clean                   # Interactive system cleaner
  python3 app.py clean --dry-run         # Preview reclaimable disk space
  python3 app.py install myapp.tar.gz    # Install portable app tarball from CLI
  python3 app.py list                    # List all managed apps
  python3 app.py --install-desktop-entry # Add Clinux to Linux app launcher
        """
    )

    parser.add_argument("--port", "-p", type=int, default=None, help="Port to bind server to (default: 8421)")
    parser.add_argument("--host", "-H", type=str, default="127.0.0.1", help="Host address (default: 127.0.0.1)")
    parser.add_argument("--no-browser", action="store_true", help="Do not automatically open browser")
    parser.add_argument("--keep-alive", action="store_true", help="Keep server running even after all browser tabs are closed")
    parser.add_argument("--db", type=str, default=None, help="Custom SQLite database file path")
    parser.add_argument("--install-desktop-entry", action="store_true", help="Install desktop shortcut for TarGz Manager itself")

    subparsers = parser.add_subparsers(dest="command", help="CLI commands (optional)")

    subparsers.add_parser("list", help="List all managed applications")

    subparsers.add_parser("scan", help="Scan system for unmanaged manual apps and tarballs")

    subparsers.add_parser("import-discovered", help="Scan and automatically import all unmanaged apps into database")

    p_inspect = subparsers.add_parser("inspect", help="Inspect a tarball archive")
    p_inspect.add_argument("archive", help="Path to archive file (.tar.gz, .tgz, .tar.xz, .zip)")

    p_install = subparsers.add_parser("install", help="Install an application from tarball")
    p_install.add_argument("archive", help="Path to archive file")
    p_install.add_argument("--name", help="Custom app slug name")
    p_install.add_argument("--display-name", help="Display name")
    p_install.add_argument("--version", help="App version")
    p_install.add_argument("--category", default="Utility", help="Category (default: Utility)")
    p_install.add_argument("--dest", help="Custom destination folder")
    p_install.add_argument("--no-desktop", action="store_true", help="Do not create .desktop shortcut")
    p_install.add_argument("--no-symlink", action="store_true", help="Do not create ~/.local/bin symlink")

    p_update = subparsers.add_parser("update", help="Update existing app with new tarball")
    p_update.add_argument("app_id_or_name", help="App ID or slug name")
    p_update.add_argument("archive", help="Path to new archive file")
    p_update.add_argument("--version", help="New version string")

    p_remove = subparsers.add_parser("remove", help="Uninstall application")
    p_remove.add_argument("app_id_or_name", help="App ID or slug name")
    p_remove.add_argument("--keep-files", action="store_true", help="Unregister only, keep files on disk")

    p_launch = subparsers.add_parser("launch", help="Launch an application")
    p_launch.add_argument("app_id_or_name", help="App ID or slug name")

    p_clean = subparsers.add_parser("clean", help="Find and clean package manager caches and junk files")
    p_clean.add_argument("--all", "-a", action="store_true", help="Clean all detected safe caches immediately")
    p_clean.add_argument("--targets", "-t", type=str, help="Comma-separated target IDs to clean (e.g. yay,pip,thumbnails)")
    p_clean.add_argument("--dry-run", action="store_true", help="Scan and list without deleting")

    args = parser.parse_args()

    if args.install_desktop_entry:
        install_desktop_shortcut_for_manager()
        if not args.command:
            return

    db_path = Path(args.db) if args.db else None
    db = Database(db_path)
    installer = Installer(db)

    from targz_manager.scanner import SystemScanner
    scanner = SystemScanner(db, installer)

    if args.command == "list":
        apps = db.list_apps()
        print_cli_table(apps)
        return

    elif args.command == "scan":
        print("\n🔍 Scanning system for unmanaged applications and tarballs...")
        discovered = scanner.discover_unmanaged_apps()
        if not discovered:
            print("✓ No unmanaged applications found. Everything is organized!\n")
            return

        print("\n" + "=" * 85)
        print(f"{'TYPE':<15} {'NAME':<22} {'VERSION':<10} {'SIZE':<10} {'LOCATION'}")
        print("-" * 85)
        for d in discovered:
            src_label = "Desktop Icon" if d.get("source") == "desktop_file" else ("Tarball" if d.get("is_tarball_archive") else "Folder Scan")
            loc = d.get("install_path") or d.get("archive_path", "")
            if len(loc) > 28:
                loc = "..." + loc[-25:]
            print(f"{src_label:<15} {d['display_name'][:20]:<22} {d.get('version', '1.0')[:8]:<10} {d.get('size_formatted', '-'):<10} {loc}")
        print("=" * 85)
        print(f"Found {len(discovered)} unmanaged application(s).")
        print("To import all: python3 app.py import-discovered\n")
        return

    elif args.command == "import-discovered":
        print("\n🔍 Scanning and importing unmanaged applications...")
        discovered = scanner.discover_unmanaged_apps()
        if not discovered:
            print("✓ No unmanaged applications found to import.\n")
            return

        imported_count = 0
        for d in discovered:
            try:
                if d.get("is_tarball_archive") and d.get("archive_path"):
                    print(f"  • Installing tarball: {d['display_name']}...")
                    installer.install_app(
                        archive_path=d['archive_path'],
                        name=d['name'],
                        display_name=d['display_name'],
                        version=d['version'],
                        create_desktop=True,
                        create_bin_symlink=True
                    )
                else:
                    print(f"  • Registering: {d['display_name']} ({d['install_path']})...")
                    installer.register_existing_app(
                        name=d['name'],
                        install_path=d['install_path'],
                        executable_path=d['executable_path'],
                        display_name=d['display_name'],
                        version=d.get('version', '1.0.0'),
                        category=d.get('category', 'Utility'),
                        icon_path=d.get('icon_path'),
                        create_desktop=True,
                        create_bin_symlink=True,
                        description=d.get('description', '')
                    )
                imported_count += 1
            except Exception as e:
                print(f"    ⚠ Skipped {d['display_name']}: {e}")

        print(f"\n✓ Successfully imported {imported_count} application(s) into database!")
        apps = db.list_apps()
        print_cli_table(apps)
        return

    elif args.command == "inspect":
        try:
            info = installer.inspect_archive(args.archive)
            print("\n" + "=" * 60)
            print(f"Archive:       {info['archive_filename']}")
            print(f"Size:          {Database.format_size(info['archive_size_bytes'])}")
            print(f"Uncompressed:  {Database.format_size(info['uncompressed_size_bytes'])} ({info['total_files']} files)")
            print(f"Guessed Name:  {info['guessed_name']} ({info['guessed_display_name']})")
            print(f"Guessed Ver:   {info['guessed_version']}")
            print(f"Wrapper Dir:   {info['wrapper_folder'] if info['has_wrapper_folder'] else 'None'}")
            print("\nDetected Executables:")
            for ex in info['executables']:
                print(f"  • {ex['path']} (score: {ex['score']})")
            print("\nDetected Icons:")
            for ic in info['icons']:
                print(f"  • {ic['path']}")
            print("=" * 60 + "\n")
        except ArchiveError as e:
            print(f"Error inspecting archive: {e}", file=sys.stderr)
            sys.exit(1)
        return

    elif args.command == "install":
        try:
            insp = installer.inspect_archive(args.archive)
            name = args.name or insp["guessed_name"]
            disp_name = args.display_name or insp["guessed_display_name"]
            ver = args.version or insp["guessed_version"]

            print(f"Installing {disp_name} (v{ver})...")
            app = installer.install_app(
                archive_path=args.archive,
                name=name,
                display_name=disp_name,
                version=ver,
                category=args.category,
                install_path=args.dest,
                create_desktop=not args.no_desktop,
                create_bin_symlink=not args.no_symlink
            )
            print(f"✓ Successfully installed {app['display_name']}!")
            print(f"  Install Directory: {app['install_path']}")
            print(f"  Executable:        {app['executable_path']}")
            if app.get("desktop_entry_path"):
                print(f"  Desktop Shortcut:  {app['desktop_entry_path']}")
            if app.get("symlink_path"):
                print(f"  Terminal Symlink:  {app['symlink_path']}")
        except Exception as e:
            print(f"Installation failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    elif args.command == "update":
        app_ref = args.app_id_or_name
        app = None
        if app_ref.isdigit():
            app = db.get_app(int(app_ref))
        if not app:
            app = db.get_app_by_name(app_ref)
        if not app:
            print(f"Error: Application '{app_ref}' not found in database.", file=sys.stderr)
            sys.exit(1)

        try:
            print(f"Updating {app['display_name']} with {args.archive}...")
            updated = installer.update_app(
                app_id=app["id"],
                archive_path=args.archive,
                new_version=args.version
            )
            print(f"✓ Updated {updated['display_name']} to v{updated['version']} successfully!")
        except Exception as e:
            print(f"Update failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    elif args.command == "remove":
        app_ref = args.app_id_or_name
        app = None
        if app_ref.isdigit():
            app = db.get_app(int(app_ref))
        if not app:
            app = db.get_app_by_name(app_ref)
        if not app:
            print(f"Error: Application '{app_ref}' not found in database.", file=sys.stderr)
            sys.exit(1)

        try:
            res = installer.uninstall_app(
                app_id=app["id"],
                delete_files=not args.keep_files,
                delete_desktop=True,
                delete_symlink=True
            )
            print(f"✓ Uninstalled {res['app_name']}. Freed {Database.format_size(res['bytes_freed'])}.")
        except Exception as e:
            print(f"Removal failed: {e}", file=sys.stderr)
            sys.exit(1)
        return

    elif args.command == "launch":
        if not args.target:
            print("Error: App slug or ID required. Usage: python3 app.py launch <app_slug_or_id>")
            sys.exit(1)
        app_id_or_slug = args.target
        app = installer.db.get_app(int(app_id_or_slug)) if app_id_or_slug.isdigit() else installer.db.get_app_by_slug(app_id_or_slug)
        if not app:
            print(f"Error: App '{app_id_or_slug}' not found.")
            sys.exit(1)
        installer.launch_app(app["id"])
        print(f"✓ Launched {app['display_name']}")
        return

    elif args.command == "import-discovered":
        scanner = SystemScanner(installer.db, installer)
        discovered = scanner.scan_all()
        print(f"\n🔍 Discovered {len(discovered)} unmanaged app(s) or archive(s):")
        for item in discovered:
            print(f"  • [{item['source_type']}] {item['display_name']} -> {item['path']}")
            if item.get("can_import_directly"):
                try:
                    res = scanner.import_discovered(item["key"])
                    print(f"    ✓ Imported as '{res['display_name']}'")
                except Exception as e:
                    print(f"    ⚠ Import failed: {e}")
        print("\n✨ Discovery scan & import complete.\n")
        return

    elif args.command == "clean":
        print("\n🔍 Scanning package manager caches and junk files...")
        scan_data = cleaner.scan()

        print(f"\n{'='*85}")
        print(f"{'ID':<14} {'NAME':<24} {'CATEGORY':<16} {'SIZE':<10} {'FILES':<8} {'PATH'}")
        print(f"{'-'*85}")
        for t in scan_data["targets"]:
            p_str = t['path']
            if len(p_str) > 28:
                p_str = "..." + p_str[-25:]
            print(f"{t['id']:<14} {t['name'][:22]:<24} {t['category'][:14]:<16} {t['size_formatted']:<10} {t['file_count']:<8} {p_str}")
        print(f"{'='*85}")
        print(f"Total reclaimable space: \033[1;32m{scan_data['total_size_formatted']}\033[0m ({scan_data['total_files']} files)\n")

        if args.dry_run:
            print("Dry run completed. No files were deleted.")
            return

        to_clean = []
        if args.targets:
            to_clean = [t.strip() for t in args.targets.split(",") if t.strip()]
        elif args.all:
            to_clean = [t["id"] for t in scan_data["targets"]]
        else:
            print("Select targets to clean (comma-separated IDs, 'all' for everything, or 'q' to quit):")
            try:
                user_in = input("> ").strip()
                if not user_in or user_in.lower() == 'q':
                    print("Cancelled.")
                    return
                if user_in.lower() == 'all':
                    to_clean = [t["id"] for t in scan_data["targets"]]
                else:
                    to_clean = [t.strip() for t in user_in.split(",") if t.strip()]
            except (KeyboardInterrupt, EOFError):
                print("\nCancelled.")
                return

        if to_clean:
            res = cleaner.clean(to_clean)
            print(f"\n✨ Clean complete. Total space freed: {res['freed_formatted']}\n")
        return

    target_port = args.port or 8421
    host = args.host
    url = f"http://{host}:{target_port}/"

    if check_server_running(host, target_port):
        print(f"✓ TarGz Manager is already running at {url}. Opening browser tab...")
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
        print("\nStopping TarGz App Manager server... Goodbye!")
    finally:
        try:
            server.shutdown()
            server.server_close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
