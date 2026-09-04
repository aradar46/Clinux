import os
import re
import shlex
import shutil
import subprocess
from pathlib import Path
from typing import Dict, List, Any

class SystemDoctor:
    def __init__(self, cleaner=None):
        self.cleaner = cleaner

    def check_failed_services(self) -> List[Dict[str, Any]]:
        problems = []
        try:
            res = subprocess.run(["systemctl", "list-units", "--state=failed", "--no-pager", "--no-legend"], capture_output=True, text=True)
            if res.returncode == 0:
                for line in res.stdout.strip().split("\n"):
                    if not line.strip():
                        continue
                    parts = line.split()
                    if len(parts) > 0:
                        service = parts[0]
                        problems.append({
                            "type": "failed_service",
                            "item": service,
                            "description": f"systemd service {service} failed",
                            "fix_command": f"sudo systemctl restart {service}",
                            "fixable": True
                        })
        except Exception:
            pass
        return problems

    def check_old_kernels(self) -> List[Dict[str, Any]]:
        problems = []
        try:
            current = subprocess.run(["uname", "-r"], capture_output=True, text=True).stdout.strip()
            if os.path.exists("/boot"):
                kernels = []
                for f in os.listdir("/boot"):
                    if f.startswith("vmlinuz-") or f.startswith("initramfs-"):
                        ver = f.replace("vmlinuz-", "").replace("initramfs-", "").replace(".img", "")
                        if ver not in kernels and "fallback" not in ver:
                            kernels.append(ver)

                for k in kernels:
                    if k != current:
                        problems.append({
                            "type": "old_kernel",
                            "item": k,
                            "description": f"Old kernel version {k} is installed but not running.",
                            "fix_command": None,
                            "fixable": False
                        })
        except Exception:
            pass
        return problems

    def check_broken_desktop_entries(self) -> List[Dict[str, Any]]:
        problems = []
        dirs_to_check = [
            Path.home() / ".local" / "share" / "applications",
            Path("/usr/share/applications")
        ]

        for d in dirs_to_check:
            if not d.exists():
                continue
            try:
                for entry in d.iterdir():
                    if entry.is_file() and entry.name.endswith(".desktop"):
                        try:
                            content = entry.read_text(encoding="utf-8")
                            for line in content.split("\n"):
                                if line.startswith("Exec="):
                                    exec_cmd = line.split("=", 1)[1].strip()
                                    cmd = exec_cmd.split()[0].strip('"\'')
                                    if not shutil.which(cmd):
                                        if not os.path.exists(cmd) and not cmd.startswith("%"):
                                            problems.append({
                                                "type": "broken_desktop_entry",
                                                "item": entry.name,
                                                "description": f"Broken desktop entry {entry.name} points to missing executable '{cmd}'",
                                                "fix_command": f"rm '{entry}'",
                                                "fixable": True,
                                                "path": str(entry)
                                            })
                                    break
                        except Exception:
                            pass
            except Exception:
                pass
        return problems

    def check_network(self) -> List[Dict[str, Any]]:
        problems = []
        try:
            res = subprocess.run(["ping", "-c", "1", "-W", "2", "8.8.8.8"], capture_output=True)
            if res.returncode != 0:
                problems.append({
                    "type": "network",
                    "item": "internet",
                    "description": "Internet connectivity check failed (ping 8.8.8.8)",
                    "fix_command": "sudo systemctl restart NetworkManager",
                    "fixable": True
                })
        except Exception:
            pass
        return problems

    def check_filesystem(self) -> List[Dict[str, Any]]:
        problems = []
        try:
            res = subprocess.run(["df", "-h"], capture_output=True, text=True)
            if res.returncode == 0:
                lines = res.stdout.strip().split("\n")[1:]
                for line in lines:
                    parts = line.split()
                    if len(parts) >= 6:
                        use_pct = parts[4].replace('%', '')
                        if use_pct.isdigit() and int(use_pct) >= 90:
                            mount = parts[5]
                            problems.append({
                                "type": "filesystem",
                                "item": mount,
                                "description": f"Filesystem mounted at {mount} is {use_pct}% full",
                                "fix_command": "python3 app.py clean",
                                "fixable": False
                            })
        except Exception:
            pass
        return problems

    def scan(self) -> Dict[str, Any]:
        results = {
            "failed_services": self.check_failed_services(),
            "old_kernels": self.check_old_kernels(),
            "broken_desktop_entries": self.check_broken_desktop_entries(),
            "network": self.check_network(),
            "filesystem": self.check_filesystem(),
            "reclaimable_cache": 0,
            "reclaimable_cache_formatted": "0 B"
        }

        if self.cleaner:
            try:
                c_scan = self.cleaner.scan()
                results["reclaimable_cache"] = c_scan.get("total_size_bytes", 0)
                results["reclaimable_cache_formatted"] = c_scan.get("total_size_formatted", "0 B")
            except Exception:
                pass

        problems = (
            results["failed_services"] +
            results["old_kernels"] +
            results["broken_desktop_entries"] +
            results["network"] +
            results["filesystem"]
        )

        results["all_problems"] = problems
        return results

    def fix(self, problem: Dict[str, Any]) -> bool:
        cmd = problem.get("fix_command")
        if problem.get("type") == "broken_desktop_entry":
            path = problem.get("path")
            if path and os.path.exists(path):
                try:
                    os.remove(path)
                    return True
                except Exception:
                    return False

        if not cmd:
            return False

        try:
            cmd_args = shlex.split(cmd)
            if not cmd_args:
                return False
            res = subprocess.run(cmd_args, capture_output=True, text=True, check=True)
            return res.returncode == 0
        except Exception:
            return False
