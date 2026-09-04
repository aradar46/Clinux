import os
import subprocess
import ast
import re
from pathlib import Path
from typing import Dict, Any, List

from .db import Database
from .dotfiles_manager import DotfilesManager
from .ai_manager import SkillManager

class MachineManager:
    def __init__(self, db: Database):
        self.db = db
        self.dm = DotfilesManager()
        self.sm = SkillManager()

    def _parse_toml(self, content: str) -> Dict[str, Any]:
        result = {}
        current_section = None
        array_of_tables_key = None

        lines = content.splitlines()
        i = 0
        while i < len(lines):
            line = lines[i].strip()
            if not line or line.startswith('#'):
                i += 1
                continue

            # Array of tables like [[portable_apps]]
            mat_aot = re.match(r'^\[\[(.*?)\]\]$', line)
            if mat_aot:
                key = mat_aot.group(1).strip()
                if key not in result:
                    result[key] = []
                result[key].append({})
                current_section = None
                array_of_tables_key = key
                i += 1
                continue

            mat = re.match(r'^\[(.*?)\]$', line)
            if mat:
                current_section = mat.group(1).strip()
                if current_section not in result:
                    result[current_section] = {}
                array_of_tables_key = None
                i += 1
                continue

            if '=' in line:
                key, val = line.split('=', 1)
                key = key.strip().strip('"')
                val = val.strip()

                parsed_val = None
                if val.startswith('"""'):
                    multiline_str = [val[3:]] if val[3:] else []
                    i += 1
                    while i < len(lines):
                        if lines[i].strip().endswith('"""'):
                            last_line = lines[i].replace('"""', '')
                            if last_line:
                                multiline_str.append(last_line)
                            break
                        multiline_str.append(lines[i])
                        i += 1
                    parsed_val = "\n".join(multiline_str)
                elif val == "true":
                    parsed_val = True
                elif val == "false":
                    parsed_val = False
                elif val.startswith('"') and val.endswith('"'):
                    parsed_val = val[1:-1].replace('\\"', '"').replace('\\\\', '\\')
                elif val.startswith('['):
                    # accumulate until closing ']' if multiline array
                    array_str = val
                    while not array_str.rstrip().endswith(']') and i + 1 < len(lines):
                        i += 1
                        array_str += " " + lines[i].strip()
                    try:
                        parsed_val = ast.literal_eval(array_str)
                    except Exception:
                        parsed_val = []
                else:
                    try:
                        parsed_val = ast.literal_eval(val)
                    except Exception:
                        parsed_val = val

                if array_of_tables_key:
                    result[array_of_tables_key][-1][key] = parsed_val
                elif current_section:
                    result[current_section][key] = parsed_val
                else:
                    result[key] = parsed_val
            i += 1

        return result

    def export_machine(self, output_path: str):
        # 1. Dotfiles
        dotfiles_status = self.dm.get_status()
        stowed_packages = [p['name'] for p in dotfiles_status.get('packages', []) if p.get('stowed')]
        repo_path = dotfiles_status.get('repo_path', '')

        # 2. Git config
        git_config = {}
        try:
            res = subprocess.run(["git", "config", "--global", "-l"], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                if "=" in line:
                    k, v = line.split("=", 1)
                    git_config[k.strip()] = v.strip()
        except Exception:
            pass

        # 3. Installed packages
        apt_packages = []
        try:
            res = subprocess.run(["apt-mark", "showmanual"], capture_output=True, text=True)
            if res.returncode == 0:
                apt_packages = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            pass

        pacman_packages = []
        try:
            res = subprocess.run(["pacman", "-Qqen"], capture_output=True, text=True)
            if res.returncode == 0:
                pacman_packages = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            pass

        # 4. Portable apps
        portable_apps = self.db.list_apps()
        apps_data = []
        for app in portable_apps:
            apps_data.append({
                "name": app.get("name", ""),
                "display_name": app.get("display_name", ""),
                "version": app.get("version", ""),
            })

        # 5. Python versions
        python_versions = []
        try:
            res = subprocess.run(["pyenv", "versions", "--bare"], capture_output=True, text=True)
            if res.returncode == 0:
                python_versions = [line.strip() for line in res.stdout.splitlines() if line.strip()]
        except Exception:
            pass

        if not python_versions:
            try:
                res = subprocess.run(["python3", "--version"], capture_output=True, text=True)
                if res.returncode == 0:
                    python_versions = [res.stdout.strip().replace("Python ", "")]
            except Exception:
                pass

        # 6. Node versions
        node_versions = []
        try:
            res = subprocess.run(["node", "--version"], capture_output=True, text=True)
            if res.returncode == 0:
                node_versions = [res.stdout.strip()]
        except Exception:
            pass

        # 7. AI skills
        skills = self.sm.get_all_skills()
        active_skills = [s['name'] for s in skills if s.get('active')]

        # 8. GNOME settings
        gnome_settings = ""
        try:
            res = subprocess.run(["dconf", "dump", "/"], capture_output=True, text=True)
            if res.returncode == 0:
                gnome_settings = res.stdout
        except Exception:
            pass

        # Generate TOML
        lines = []

        def fmt_str(v):
            v = str(v).replace("\\", "\\\\").replace('"', '\\"')
            return f'"{v}"'

        lines.append("[dotfiles]")
        lines.append(f"repo = {fmt_str(repo_path)}")
        lines.append(f"packages = {repr(stowed_packages)}")
        lines.append("")

        lines.append("[git_config]")
        for k, v in git_config.items():
            lines.append(f'"{k}" = {fmt_str(v)}')
        lines.append("")

        lines.append("[packages]")
        if apt_packages:
            lines.append(f"apt = {repr(apt_packages)}")
        if pacman_packages:
            lines.append(f"pacman = {repr(pacman_packages)}")
        lines.append("")

        if apps_data:
            for app in apps_data:
                lines.extend((
                    "[[portable_apps]]",
                    f'name = {fmt_str(app["name"])}',
                    f'display_name = {fmt_str(app["display_name"])}',
                    f'version = {fmt_str(app["version"])}',
                    ""
                ))

        lines.append("[python]")
        lines.append(f"versions = {repr(python_versions)}")
        lines.append("")

        lines.append("[node]")
        lines.append(f"versions = {repr(node_versions)}")
        lines.append("")

        lines.append("[ai_skills]")
        lines.append(f"active = {repr(active_skills)}")
        lines.append("")

        lines.append("[gnome_settings]")
        if gnome_settings:
            lines.append(f'dconf = """\n{gnome_settings}\n"""')
        else:
            lines.append('dconf = ""')

        with open(output_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return output_path

    def restore_machine(self, input_path: str) -> List[str]:
        if not os.path.exists(input_path):
            return [f"Error: Manifest file '{input_path}' not found."]

        with open(input_path, "r", encoding="utf-8") as f:
            content = f.read()

        data = self._parse_toml(content)

        results = []

        # 1. Dotfiles
        dotfiles = data.get("dotfiles", {})
        stowed = dotfiles.get("packages", [])
        if stowed:
            results.append(f"Dotfiles: Stowing {len(stowed)} packages...")
            for pkg in stowed:
                res = self.dm.run_command("stow", package=pkg)
                results.append(f"  - {pkg}: {'Success' if res.get('success') else 'Failed (' + str(res.get('error')) + ')'}")

        # 2. Git config
        git_config = data.get("git_config", {})
        if git_config:
            results.append(f"Git: Applying {len(git_config)} config entries...")
            for k, v in git_config.items():
                subprocess.run(["git", "config", "--global", k, str(v)], capture_output=True)
            results.append("  - Done")

        # 3. Installed packages
        packages = data.get("packages", {})
        apt_pkgs = packages.get("apt", [])
        if apt_pkgs:
            results.append(f"APT: Discovered {len(apt_pkgs)} packages.")
            results.append(f"  -> To install, run: sudo apt-get install -y {' '.join(apt_pkgs[:10])}... (see manifest for full list)")

        pacman_pkgs = packages.get("pacman", [])
        if pacman_pkgs:
            results.append(f"Pacman: Discovered {len(pacman_pkgs)} packages.")
            results.append(f"  -> To install, run: sudo pacman -S --needed {' '.join(pacman_pkgs[:10])}... (see manifest for full list)")

        # 4. Portable apps
        apps = data.get("portable_apps", [])
        if apps:
            results.append(f"Portable Apps: Found {len(apps)} apps in manifest.")
            for app in apps:
                results.append(f"  - Needs install: {app.get('display_name', app.get('name'))} (v{app.get('version')})")

        # 5. Python/Node
        py_vers = data.get("python", {}).get("versions", [])
        if py_vers:
            results.append(f"Python: Versions {', '.join(py_vers)} expected.")

        node_vers = data.get("node", {}).get("versions", [])
        if node_vers:
            results.append(f"Node: Versions {', '.join(node_vers)} expected.")

        # 6. AI skills
        ai_skills = data.get("ai_skills", {}).get("active", [])
        if ai_skills:
            results.append(f"AI Skills: Activating {len(ai_skills)} skills...")
            for skill in ai_skills:
                res = self.sm.activate_skill(skill)
                if res.get("success"):
                    results.append(f"  - {skill}: Activated")
                else:
                    results.append(f"  - {skill}: Failed ({res.get('error')})")

        # 7. GNOME settings
        gnome = data.get("gnome_settings", {}).get("dconf", "")
        if gnome:
            results.append("GNOME: Restoring dconf settings...")
            try:
                p = subprocess.run(["dconf", "load", "/"], input=gnome, text=True, capture_output=True)
                if p.returncode == 0:
                    results.append("  - Settings loaded successfully.")
                else:
                    results.append(f"  - Failed to load settings: {p.stderr.strip()}")
            except Exception as e:
                results.append(f"  - Failed to load settings: {e}")

        return results
