import os
import subprocess
from pathlib import Path
from typing import Dict, List, Any
from .db import Database

class DiskAnalyzer:
    def __init__(self, ai_storage=None, cleaner=None):
        self.ai_storage = ai_storage
        self.cleaner = cleaner

    def analyze(self) -> Dict[str, Any]:
        home_path = Path.home()

        ai_size = 0
        ai_size_formatted = "0 B"
        if self.ai_storage:
            try:
                ai_data = self.ai_storage.scan_all()
                ai_size = ai_data.get("total_size_bytes", 0)
                ai_size_formatted = ai_data.get("total_size_formatted", "0 B")
            except Exception:
                pass

        dev_cache_size = 0
        pkg_cache_size = 0
        if self.cleaner:
            try:
                c_scan = self.cleaner.scan()
                for target in c_scan.get("targets", []):
                    if target["category"] == "developer":
                        dev_cache_size += target["size_bytes"]
                    elif target["category"] == "package_managers":
                        pkg_cache_size += target["size_bytes"]
            except Exception:
                pass

        home_size = 0
        try:
            res = subprocess.run(["du", "-s", "-k", str(home_path)], capture_output=True, text=True)
            if res.returncode == 0:
                home_size = int(res.stdout.split()[0]) * 1024
        except Exception:
            pass

        # Real filesystem disk usage via shutil.disk_usage
        import shutil
        total_bytes, used_bytes, free_bytes = 0, 0, 0
        try:
            usage = shutil.disk_usage(home_path)
            total_bytes = usage.total
            used_bytes = usage.used
            free_bytes = usage.free
        except Exception:
            pass

        disk_pct = round((used_bytes / total_bytes * 100)) if total_bytes > 0 else 0

        # Calculate system health dynamically
        failed_services_count = 0
        try:
            res = subprocess.run(["systemctl", "--failed", "--quiet"], capture_output=True, text=True)
            if res.returncode == 0 and res.stdout.strip():
                failed_services_count = len([line for line in res.stdout.strip().splitlines() if line])
        except Exception:
            pass

        health_penalty = 0.0
        if disk_pct > 90:
            health_penalty += (disk_pct - 90) * 3 + 10
        elif disk_pct > 80:
            health_penalty += (disk_pct - 80) * 1.5

        health_penalty += failed_services_count * 10

        health_pct = max(10, min(100, round(100 - health_penalty)))
        if health_pct >= 85:
            health_status = "ALL SYSTEMS OPERATIONAL"
        elif health_pct >= 60:
            health_status = "ATTENTION REQUIRED"
        else:
            health_status = "CRITICAL DEGRADATION"

        filled_blocks = round(health_pct / 100 * 24)
        ascii_bar = "█" * filled_blocks + "░" * (24 - filled_blocks)
        health_str = f"SYSTEM HEALTH: [{ascii_bar}] {health_pct}% — {health_status}"

        return {
            "total_bytes": total_bytes,
            "total_formatted": Database.format_size(total_bytes),
            "used_bytes": used_bytes,
            "used_formatted": Database.format_size(used_bytes),
            "free_bytes": free_bytes,
            "free_formatted": Database.format_size(free_bytes),
            "usage_percent": disk_pct,
            "health_percent": health_pct,
            "health_status": health_status,
            "health_ascii_bar": ascii_bar,
            "health_display_str": health_str,
            "failed_services_count": failed_services_count,
            "home_size_bytes": home_size,
            "home_size_formatted": Database.format_size(home_size),
            "ai_models_size_bytes": ai_size,
            "ai_models_size_formatted": ai_size_formatted,
            "dev_caches_size_bytes": dev_cache_size,
            "dev_caches_size_formatted": Database.format_size(dev_cache_size),
            "pkg_caches_size_bytes": pkg_cache_size,
            "pkg_caches_size_formatted": Database.format_size(pkg_cache_size),
        }
