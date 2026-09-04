"""
CLI parsing and execution logic for Clinux.
"""

import sys
import json
import argparse
import webbrowser
import threading
import subprocess
import urllib.request
from pathlib import Path
from typing import List, Optional

from clinux.runner import runner
from clinux.config import Config
from clinux.paths import DEFAULT_DESKTOP_DIR, DEFAULT_OPT_DIR, DEFAULT_BIN_DIR
from clinux.modules import registry

from targz_manager.db import Database
from targz_manager.installer import Installer
from targz_manager.server import create_server


def open_browser_tab(url: str):
    """Open URL using xdg-open directly or Python webbrowser as fallback."""
    try:
        subprocess.Popen(["xdg-open", url], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception:
        webbrowser.open(url)


def check_server_running(host: str, port: int) -> bool:
    """Check if Clinux is already active on host:port"""
    try:
        url = f"http://{host}:{port}/api/system-info"
        req = urllib.request.Request(url, headers={"User-Agent": "ClinuxLauncher"})
        with urllib.request.urlopen(req, timeout=0.5) as resp:
            return resp.status == 200
    except Exception:
        return False


def install_desktop_shortcut_for_manager():
    """Install .desktop file for Clinux into ~/.local/share/applications"""
    script_path = Path(__file__).resolve().parent.parent / "app.py"
    icon_path = script_path.parent / "targz_manager" / "static" / "icon.png"
    desktop_file = DEFAULT_DESKTOP_DIR / "clinux.desktop"

    content = [
        "[Desktop Entry]",
        "Type=Application",
        "Version=1.0",
        "Name=Clinux",
        "GenericName=Linux Cleaner & Portable App Manager",
        "Comment=Clean system caches, purge package manager junk, and manage portable Linux applications",
        f'Exec=python3 "{script_path}"',
        f"Path={script_path.parent}",
        f"Icon={icon_path}",
        "Terminal=false",
        "Categories=System;Utility;PackageManager;Settings;",
        "StartupNotify=false"
    ]

    DEFAULT_DESKTOP_DIR.mkdir(parents=True, exist_ok=True)
    with open(desktop_file, "w", encoding="utf-8") as f:
        f.write("\n".join(content) + "\n")

    try:
        desktop_file.chmod(0o755)
    except Exception:
        pass

    try:
        runner.run(["update-desktop-database", str(DEFAULT_DESKTOP_DIR)], check=False)
    except Exception:
        pass

    print(f"✓ Installed Clinux desktop shortcut to: {desktop_file}")


def print_cli_table(apps: List[dict]):
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


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Clinux - Linux Cleaner & Portable App Manager",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python3 app.py                         # Launch GUI web server and open browser
  python3 app.py --port 8080             # Run on custom port
  python3 app.py clean                   # Interactive system cleaner
  python3 app.py clean --dry-run         # Preview reclaimable disk space
  python3 app.py clean --json            # Output structured scan result in JSON
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
    parser.add_argument("--json", action="store_true", help="Output results in JSON format")
    parser.add_argument("--dry-run", action="store_true", help="Simulate command execution without making changes")
    parser.add_argument("--install-desktop-entry", action="store_true", help="Install desktop shortcut for TarGz Manager itself")

    subparsers = parser.add_subparsers(dest="command", help="CLI commands (optional)")

    p_list = subparsers.add_parser("list", help="List all managed applications")
    p_list.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_scan = subparsers.add_parser("scan", help="Scan system for unmanaged manual apps and tarballs")
    p_scan.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_import = subparsers.add_parser("import-discovered", help="Scan and automatically import all unmanaged apps into database")
    p_import.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_inspect = subparsers.add_parser("inspect", help="Inspect a tarball archive")
    p_inspect.add_argument("archive", help="Path to archive file (.tar.gz, .tgz, .tar.xz, .zip)")
    p_inspect.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_install = subparsers.add_parser("install", help="Install an application from tarball")
    p_install.add_argument("archive", help="Path to archive file")
    p_install.add_argument("--name", help="Custom app slug name")
    p_install.add_argument("--display-name", help="Display name")
    p_install.add_argument("--version", help="App version")
    p_install.add_argument("--category", default="Utility", help="Category (default: Utility)")
    p_install.add_argument("--dest", help="Custom destination folder")
    p_install.add_argument("--no-desktop", action="store_true", help="Do not create .desktop shortcut")
    p_install.add_argument("--no-symlink", action="store_true", help="Do not create ~/.local/bin symlink")
    p_install.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_update = subparsers.add_parser("update", help="Update existing app with new tarball")
    p_update.add_argument("app_id_or_name", help="App ID or slug name")
    p_update.add_argument("archive", help="Path to new archive file")
    p_update.add_argument("--version", help="New version string")
    p_update.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_remove = subparsers.add_parser("remove", help="Uninstall application")
    p_remove.add_argument("app_id_or_name", help="App ID or slug name")
    p_remove.add_argument("--keep-files", action="store_true", help="Unregister only, keep files on disk")
    p_remove.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_launch = subparsers.add_parser("launch", help="Launch an application")
    p_launch.add_argument("app_id_or_name", help="App ID or slug name")

    p_clean = subparsers.add_parser("clean", help="Find and clean package manager caches and junk files")
    p_clean.add_argument("--all", "-a", action="store_true", help="Clean all detected safe caches immediately")
    p_clean.add_argument("--targets", "-t", type=str, help="Comma-separated target IDs to clean (e.g. yay,pip,thumbnails)")
    p_clean.add_argument("--dry-run", action="store_true", help="Scan and list without deleting")
    p_clean.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_doctor = subparsers.add_parser("doctor", help="System Doctor: Diagnose and fix system issues")
    p_doctor.add_argument("--fix", action="store_true", help="Automatically attempt to fix fixable issues")
    p_doctor.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_disk = subparsers.add_parser("disk", help="Disk Analyzer: Overview of disk usage")
    p_disk.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_skills = subparsers.add_parser("skills", help="Manage AI agent skills across Claude, Antigravity, and Codex")
    p_skills.add_argument("--activate", "-a", type=str, help="Skill key or category to activate")
    p_skills.add_argument("--deactivate", "-d", type=str, help="Skill key or category to deactivate")
    p_skills.add_argument("--category", "-c", action="store_true", help="Treat activate/deactivate target as category")
    p_skills.add_argument("--targets", "-t", type=str, help="Comma-separated agent targets (claude, agy, gemini, codex)")
    p_skills.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_ai_storage = subparsers.add_parser("ai-storage", help="Inspect and manage local AI model weights and agent workspaces")
    p_ai_storage.add_argument("--delete-model", type=str, help="Delete model by ID")
    p_ai_storage.add_argument("--clean-workspace", type=str, help="Clean workspace by ID")
    p_ai_storage.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_export = subparsers.add_parser("export", help="Export developer machine manifest to TOML")
    p_export.add_argument("output", nargs="?", default="clinux-machine.toml", help="Output file path")
    p_export.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_restore = subparsers.add_parser("restore", help="Restore developer machine state from manifest TOML")
    p_restore.add_argument("input", nargs="?", default="clinux-machine.toml", help="Input file path")
    p_restore.add_argument("--json", action="store_true", help="Output results in JSON format")

    p_dotfiles = subparsers.add_parser("dotfiles", help="Manage dotfiles using ~/.dotfiles/dotfiles script and GNU Stow")
    p_dotfiles.add_argument("action", nargs="?", default="status", choices=["status", "check", "apply", "update", "save", "gnome-out", "gnome-in", "stow", "unstow", "restow"], help="Action to run")
    p_dotfiles.add_argument("package", nargs="?", help="Package name for selective stow, unstow, or restow")
    p_dotfiles.add_argument("--message", "-m", help="Commit message when saving")
    p_dotfiles.add_argument("--json", action="store_true", help="Output results in JSON format")

    return parser


def _handle_list_cmd(args, is_json: bool) -> int:
    apps_mod = registry.get("apps")
    data = apps_mod.run_action("list")
    if is_json:
        print(json.dumps(data, indent=2))
    else:
        print_cli_table(data.get("apps", []))
    return 0


def _handle_clean_cmd(args, is_json: bool) -> int:
    clean_mod = registry.get("cleaner")
    scan_data = clean_mod.scan()
    if is_json:
        print(json.dumps(scan_data, indent=2))
        return 0

    print("\n🔍 Scanning package manager caches and junk files...")
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

    if getattr(args, "dry_run", False):
        print("Dry run completed. No files were deleted.")
        return 0

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
                return 0
            if user_in.lower() == 'all':
                to_clean = [t["id"] for t in scan_data["targets"]]
            else:
                to_clean = [t.strip() for t in user_in.split(",") if t.strip()]
        except (KeyboardInterrupt, EOFError):
            print("\nCancelled.")
            return 0

    if to_clean:
        res = clean_mod.run_action("clean", target_ids=to_clean)
        print(f"\n✨ Clean complete. Total space freed: {res['freed_formatted']}\n")
    return 0


def _handle_doctor_cmd(args, is_json: bool) -> int:
    sec_mod = registry.get("security")
    results = sec_mod.scan()
    if is_json:
        print(json.dumps(results, indent=2))
        return 0

    print("\n🔍 Running System Doctor...")
    print("\n" + "=" * 80)
    print("  SYSTEM DOCTOR")
    print("=" * 80)

    def print_status(count, label):
        if count > 0:
            print(f"[!] {count} {label}")
        else:
            print(f"[✓] {label.capitalize().replace('failed ', '').replace('broken ', '').replace('old ', '')} healthy")

    print_status(len(results["failed_services"]), "failed systemd services")
    print_status(len(results["old_kernels"]), "old kernels")
    if results["reclaimable_cache"] > 0:
        print(f"[!] {results['reclaimable_cache_formatted']} reclaimable cache")
    else:
        print(f"[✓] Caches clean")
    print_status(len(results["filesystem"]), "filesystem")
    print_status(len(results["network"]), "network")
    print_status(len(results["broken_desktop_entries"]), "broken desktop entries")

    problems = results["all_problems"]

    if problems:
        print(f"\nPotential fixes: {sum(1 for p in problems if p['fixable'])}")
        print("-" * 80)

        for p in problems:
            print(f"Problem: {p['description']}")
            if p['fix_command']:
                print(f"Suggested fix: {p['fix_command']}")
                if args.fix and p['fixable']:
                    print("  [Auto-fixing...]")
                    fix_res = sec_mod.run_action("fix")
                    print(f"  ✓ Auto-fix completed ({fix_res.get('fixed_count', 0)} issue(s) resolved)")
            print("-" * 40)
    else:
        print("\n✓ System is healthy!")

    print("=" * 80 + "\n")
    return 0


def _handle_disk_cmd(args, is_json: bool) -> int:
    stg_mod = registry.get("storage")
    scan_data = stg_mod.scan()
    if is_json:
        print(json.dumps(scan_data, indent=2))
        return 0

    results = scan_data["disk"]
    print("\n" + "=" * 80)
    print("  STORAGE")
    print("=" * 80)
    print(f"Home                 {results['home_size_formatted']}")
    print(f"AI Models            {results['ai_models_size_formatted']}")
    print(f"Developer caches     {results['dev_caches_size_formatted']}")
    print(f"Package caches       {results['pkg_caches_size_formatted']}")
    print("=" * 80 + "\n")
    return 0


def _handle_skills_cmd(args, is_json: bool) -> int:
    sk_mod = registry.get("skills")
    tgt_list = [t.strip() for t in args.targets.split(",")] if args.targets else None

    if args.activate:
        res = sk_mod.run_action("activate", target=args.activate, is_category=args.category, agent_targets=tgt_list)
        if is_json:
            print(json.dumps(res, indent=2))
            return 0
        if args.category:
            print(f"✓ Activated category '{args.activate}' ({res.get('count', 0)} skills).")
        else:
            if res.get("success"):
                print(f"✓ Activated skill '{args.activate}' for: {', '.join(res.get('activated_targets', []))}")
            else:
                print(f"✗ Failed to activate: {res.get('error') or res.get('errors')}")
        return 0

    if args.deactivate:
        res = sk_mod.run_action("deactivate", target=args.deactivate, is_category=args.category, agent_targets=tgt_list)
        if is_json:
            print(json.dumps(res, indent=2))
            return 0
        if args.category:
            print(f"✓ Deactivated category '{args.deactivate}'.")
        else:
            if res.get("success"):
                print(f"✓ Deactivated skill '{args.deactivate}'.")
            else:
                print(f"✗ Failed to deactivate: {res.get('error') or res.get('errors')}")
        return 0

    scan_data = sk_mod.scan()
    if is_json:
        print(json.dumps(scan_data, indent=2))
        return 0

    skills = scan_data["skills"]
    cats = scan_data["categories"]
    print("\n" + "=" * 85)
    print(f"  AI AGENT SKILLS ({len(skills)} discovered across {len(cats)} categories)")
    print("=" * 85)
    print(f"{'STATUS':<8} {'CATEGORY':<20} {'SKILL NAME':<30} {'AGENTS'}")
    print("-" * 85)
    for s in skills:
        status = "● ON" if s["active"] else "○ off"
        active_ag = [k for k, v in s["active_targets"].items() if v]
        ag_str = ", ".join(active_ag) if active_ag else "-"
        print(f"{status:<8} {s['category'][:18]:<20} {s['name'][:28]:<30} {ag_str}")
    print("=" * 85)
    print("Commands:")
    print("  python3 app.py skills --activate <category/name>")
    print("  python3 app.py skills --deactivate <category/name>")
    print("  python3 app.py skills --activate <category> --category\n")
    return 0


def _handle_ai_storage_cmd(args, is_json: bool) -> int:
    stg_mod = registry.get("storage")

    if args.delete_model:
        res = stg_mod.run_action("delete_model", model_id=args.delete_model)
        if is_json:
            print(json.dumps(res, indent=2))
            return 0
        if res.get("success"):
            print(f"✓ Deleted model '{args.delete_model}'. Freed: {res.get('freed_formatted', '-')}")
        else:
            print(f"✗ Failed to delete model: {res.get('error')}")
        return 0

    if args.clean_workspace:
        res = stg_mod.run_action("clean_workspace", workspace_id=args.clean_workspace)
        if is_json:
            print(json.dumps(res, indent=2))
            return 0
        if res.get("success"):
            print(f"✓ Cleaned workspace '{args.clean_workspace}'. Freed: {res.get('freed_formatted')}")
        else:
            print(f"✗ Failed to clean workspace: {res.get('error')}")
        return 0

    scan_data = stg_mod.scan()
    data = scan_data["ai_storage"]
    if is_json:
        print(json.dumps(data, indent=2))
        return 0

    print("\n" + "=" * 80)
    print("  LOCAL AI MODELS & WEIGHTS")
    print("=" * 80)
    if not data["models"]:
        print("  No local Hugging Face, PyTorch, or Ollama models found.")
    else:
        print(f"{'SOURCE':<14} {'NAME':<42} {'SIZE':<12} {'ID'}")
        print("-" * 80)
        for m in data["models"]:
            print(f"{m['source']:<14} {m['name'][:40]:<42} {m['size_formatted']:<12} {m['id']}")

    print("\n" + "=" * 80)
    print("  AI AGENT WORKSPACES & CACHES")
    print("=" * 80)
    if not data["workspaces"]:
        print("  No agent workspaces detected.")
    else:
        print(f"{'ID':<18} {'NAME':<36} {'SIZE':<12} {'FILES'}")
        print("-" * 80)
        for w in data["workspaces"]:
            print(f"{w['id']:<18} {w['name'][:34]:<36} {w['size_formatted']:<12} {w['file_count']}")

    print("=" * 80)
    print(f"Total AI Storage Footprint: \033[1;36m{data['total_size_formatted']}\033[0m\n")
    return 0


def _handle_export_cmd(args, is_json: bool) -> int:
    mach_mod = registry.get("machine")
    res = mach_mod.run_action("export", output_path=args.output)
    if is_json:
        print(json.dumps(res, indent=2))
        return 0
    print(f"\n📦 Export complete! Manifest saved to: {res['output_path']}\n")
    return 0


def _handle_restore_cmd(args, is_json: bool) -> int:
    mach_mod = registry.get("machine")
    res = mach_mod.run_action("restore", input_path=args.input)
    if is_json:
        print(json.dumps(res, indent=2))
        return 0
    print("\n" + "=" * 80)
    print(f"  MACHINE RESTORE RESULTS: {args.input}")
    print("=" * 80)
    for r in res.get("results", []):
        if r.startswith("Error:"):
            print(f"\033[1;31m{r}\033[0m")
        elif r.startswith("  -") or r.startswith("  ->"):
            print(r)
        else:
            print(f"\033[1;34m{r}\033[0m")
    print("=" * 80 + "\n")
    return 0


def _handle_dotfiles_cmd(args, is_json: bool) -> int:
    dot_mod = registry.get("dotfiles")
    if args.action == "status":
        st = dot_mod.scan()
        if is_json:
            print(json.dumps(st, indent=2))
            return 0
        print("\n" + "=" * 80)
        print(f"  DOTFILES STATUS: {st['repo_path']}")
        print("=" * 80)
        if not st["exists"]:
            print(f"  Repo not found at {st['repo_path']}")
        else:
            script_icon = "✓" if st["has_script"] else "✗"
            print(f"  Script:    {script_icon} {st['script_path']}")
            if st["git"]["is_git"]:
                git_state = "clean" if st["git"]["clean"] else f"dirty ({st['git']['modified_files']} modified)"
                print(f"  Branch:    {st['git']['branch']} [{git_state}]")
                print(f"  Latest:    {st['git']['last_commit']}")
            print("-" * 80)
            print(f"  {'PACKAGE':<20} {'STATUS':<15} {'ACTION'}")
            print("-" * 80)
            for p in st["packages"]:
                name = p["name"] if isinstance(p, dict) else p
                stowed = p.get("stowed", False) if isinstance(p, dict) else False
                status_str = "\033[1;32mstowed\033[0m" if stowed else "\033[1;30mnot stowed\033[0m"
                hint = f"dotfiles unstow {name}" if stowed else f"dotfiles stow {name}"
                print(f"  {name:<20} {status_str:<24} ({hint})")
        print("=" * 80 + "\n")
        return 0
    else:
        res = dot_mod.run_action("run_command", command=args.action, package=args.package, message=args.message)
        if is_json:
            print(json.dumps(res, indent=2))
            return 0
        if res.get("output"):
            print(res["output"])
        if not res.get("success"):
            print(f"✗ Command failed: {res.get('error')}")
        else:
            print(f"✓ dotfiles {args.action} completed.")
        print()
        return 0


def _handle_apps_cmd(args, is_json: bool, db: Database, installer: Installer) -> int:
    apps_mod = registry.get("apps")
    if args.command == "scan":
        scan_res = apps_mod.scan()
        if is_json:
            print(json.dumps(scan_res, indent=2))
            return 0
        discovered = scan_res["unmanaged_apps"]
        if not discovered:
            print("✓ No unmanaged applications found. Everything is organized!\n")
            return 0
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
        return 0

    elif args.command == "import-discovered":
        res = apps_mod.run_action("import_discovered")
        if is_json:
            print(json.dumps(res, indent=2))
            return 0
        print(f"\n✓ Successfully imported {res.get('count', 0)} application(s) into database!")
        print_cli_table(db.list_apps())
        return 0

    elif args.command == "inspect":
        info = installer.inspect_archive(args.archive)
        if is_json:
            print(json.dumps(info, indent=2))
            return 0
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
        return 0

    elif args.command == "install":
        insp = installer.inspect_archive(args.archive)
        name = args.name or insp["guessed_name"]
        disp_name = args.display_name or insp["guessed_display_name"]
        ver = args.version or insp["guessed_version"]

        res = apps_mod.run_action(
            "install",
            archive_path=args.archive,
            name=name,
            display_name=disp_name,
            version=ver,
            category=args.category,
            install_path=args.dest,
            create_desktop=not args.no_desktop,
            create_bin_symlink=not args.no_symlink,
        )
        app = res["app"]
        if is_json:
            print(json.dumps(app, indent=2))
            return 0
        print(f"✓ Successfully installed {app['display_name']}!")
        print(f"  Install Directory: {app['install_path']}")
        print(f"  Executable:        {app['executable_path']}")
        if app.get("desktop_entry_path"):
            print(f"  Desktop Shortcut:  {app['desktop_entry_path']}")
        if app.get("symlink_path"):
            print(f"  Terminal Symlink:  {app['symlink_path']}")
        return 0

    elif args.command == "update":
        app_ref = args.app_id_or_name
        app = db.get_app(int(app_ref)) if app_ref.isdigit() else db.get_app_by_name(app_ref)
        if not app:
            print(f"Error: Application '{app_ref}' not found in database.", file=sys.stderr)
            return 1
        updated = installer.update_app(app_id=app["id"], archive_path=args.archive, new_version=args.version)
        if is_json:
            print(json.dumps(updated, indent=2))
            return 0
        print(f"✓ Updated {updated['display_name']} to v{updated['version']} successfully!")
        return 0

    elif args.command == "remove":
        app_ref = args.app_id_or_name
        app = db.get_app(int(app_ref)) if app_ref.isdigit() else db.get_app_by_name(app_ref)
        if not app:
            print(f"Error: Application '{app_ref}' not found in database.", file=sys.stderr)
            return 1
        res = apps_mod.run_action(
            "remove",
            app_id=app["id"],
            delete_files=not args.keep_files,
            delete_desktop=True,
            delete_symlink=True,
        )
        if is_json:
            print(json.dumps(res, indent=2))
            return 0
        print(f"✓ Uninstalled {res['app_name']}. Freed {Database.format_size(res['bytes_freed'])}.")
        return 0

    elif args.command == "launch":
        app_ref = args.app_id_or_name
        app = db.get_app(int(app_ref)) if app_ref.isdigit() else db.get_app_by_name(app_ref)
        if not app:
            print(f"Error: App '{app_ref}' not found.", file=sys.stderr)
            return 1
        installer.launch_app(app["id"])
        print(f"✓ Launched {app['display_name']}")
        return 0

    return 0


def _handle_server_cmd(args, installer: Installer) -> int:
    target_port = args.port or 8421
    host = args.host
    url = f"http://{host}:{target_port}/"

    if check_server_running(host, target_port):
        print(f"✓ TarGz Manager is already running at {url}. Opening browser tab...")
        if not args.no_browser:
            open_browser_tab(url)
        return 0

    port = args.port or target_port
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
            import time
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

    return 0


def run_cli(args_list: Optional[List[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(args_list)

    is_json = getattr(args, "json", False)

    if getattr(args, "dry_run", False):
        runner.dry_run = True

    if args.install_desktop_entry:
        install_desktop_shortcut_for_manager()
        if not args.command:
            return 0

    db_path = Path(args.db) if args.db else None
    db = Database(db_path)
    installer = Installer(db)

    # CLI subcommands dispatching
    if args.command == "list":
        return _handle_list_cmd(args, is_json)
    elif args.command == "clean":
        return _handle_clean_cmd(args, is_json)
    elif args.command == "doctor":
        return _handle_doctor_cmd(args, is_json)
    elif args.command == "disk":
        return _handle_disk_cmd(args, is_json)
    elif args.command == "skills":
        return _handle_skills_cmd(args, is_json)
    elif args.command == "ai-storage":
        return _handle_ai_storage_cmd(args, is_json)
    elif args.command == "export":
        return _handle_export_cmd(args, is_json)
    elif args.command == "restore":
        return _handle_restore_cmd(args, is_json)
    elif args.command == "dotfiles":
        return _handle_dotfiles_cmd(args, is_json)
    elif args.command in ("scan", "import-discovered", "inspect", "install", "update", "remove", "launch"):
        return _handle_apps_cmd(args, is_json, db, installer)

    # Default action: Launch HTTP GUI server
    return _handle_server_cmd(args, installer)
