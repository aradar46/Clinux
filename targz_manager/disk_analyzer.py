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

        return {
            "home_size_bytes": home_size,
            "home_size_formatted": Database.format_size(home_size),
            "ai_models_size_bytes": ai_size,
            "ai_models_size_formatted": ai_size_formatted,
            "dev_caches_size_bytes": dev_cache_size,
            "dev_caches_size_formatted": Database.format_size(dev_cache_size),
            "pkg_caches_size_bytes": pkg_cache_size,
            "pkg_caches_size_formatted": Database.format_size(pkg_cache_size),
        }
