import os
import tempfile
import unittest
from pathlib import Path
import urllib.request
import json

from targz_manager.cleaner import SystemCleaner
from targz_manager.db import Database
from targz_manager.installer import Installer
from targz_manager.server import create_server


class TestSystemCleaner(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        # Create mock cache directories
        self.mock_yay = self.base_path / "cache" / "yay"
        self.mock_pip = self.base_path / "cache" / "pip"
        self.mock_trash = self.base_path / "Trash"

        self.mock_yay.mkdir(parents=True)
        self.mock_pip.mkdir(parents=True)
        self.mock_trash.mkdir(parents=True)

        # Write sample files
        (self.mock_yay / "pkg1.tar.zst").write_bytes(b"A" * 1024)
        (self.mock_yay / "pkg2.tar.zst").write_bytes(b"B" * 2048)
        (self.mock_pip / "wheel.whl").write_bytes(b"C" * 4096)

        # Instantiate cleaner with custom definitions for testing
        self.cleaner = SystemCleaner()
        self.cleaner.TARGET_DEFINITIONS = [
            {
                "id": "test_yay",
                "name": "Yay AUR Cache",
                "category": "package_managers",
                "path": self.mock_yay,
                "description": "AUR packages cache",
                "safe_to_clean": True,
                "needs_sudo": False,
                "default_checked": True,
            },
            {
                "id": "test_pip",
                "name": "Pip Cache",
                "category": "developer",
                "path": self.mock_pip,
                "description": "Python pip cache",
                "safe_to_clean": True,
                "needs_sudo": False,
                "default_checked": True,
            },
            {
                "id": "test_trash",
                "name": "User Trash",
                "category": "system",
                "path": self.mock_trash,
                "description": "Files in trash",
                "safe_to_clean": True,
                "needs_sudo": False,
                "default_checked": False,
            },
            {
                "id": "test_missing",
                "name": "Nonexistent Cache",
                "category": "developer",
                "path": self.base_path / "nonexistent",
                "description": "Does not exist",
                "safe_to_clean": True,
                "needs_sudo": False,
                "default_checked": False,
            }
        ]

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_targets(self):
        results = self.cleaner.scan()
        targets = results["targets"]

        yay_target = next((t for t in targets if t["id"] == "test_yay"), None)
        self.assertIsNotNone(yay_target)
        self.assertEqual(yay_target["file_count"], 2)
        self.assertEqual(yay_target["size_bytes"], 3072)
        self.assertTrue(yay_target["size_formatted"].startswith("3.0"))

        pip_target = next((t for t in targets if t["id"] == "test_pip"), None)
        self.assertIsNotNone(pip_target)
        self.assertEqual(pip_target["file_count"], 1)
        self.assertEqual(pip_target["size_bytes"], 4096)

        missing_target = next((t for t in targets if t["id"] == "test_missing"), None)
        self.assertIsNone(missing_target)

        self.assertEqual(results["total_size_bytes"], 7168)

    def test_clean_single_target(self):
        res = self.cleaner.clean_target("test_yay")
        self.assertTrue(res["success"])
        self.assertEqual(res["freed_bytes"], 3072)
        self.assertEqual(res["freed_files"], 2)
        self.assertTrue(self.mock_yay.exists())
        self.assertEqual(len(list(self.mock_yay.iterdir())), 0)

    def test_clean_multiple_targets(self):
        res = self.cleaner.clean(["test_yay", "test_pip"])
        self.assertEqual(res["freed_bytes"], 7168)
        self.assertEqual(len(res["results"]), 2)
        self.assertTrue(all(r["success"] for r in res["results"]))
        self.assertEqual(len(list(self.mock_yay.iterdir())), 0)
        self.assertEqual(len(list(self.mock_pip.iterdir())), 0)


class TestCleanerHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.temp_dir.name) / "test.db"
        db = Database(db_path)
        installer = Installer(db)
        cls.server = create_server(host="127.0.0.1", port=0, installer=installer)
        cls.port = cls.server.server_address[1]

        import threading
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()

    def test_cleaner_scan_api(self):
        url = f"http://127.0.0.1:{self.port}/api/cleaner/scan"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("targets", data)
            self.assertIn("total_size_bytes", data)

    def test_cleaner_clean_api(self):
        url = f"http://127.0.0.1:{self.port}/api/cleaner/clean"
        body = json.dumps({"targets": []}).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=3) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("freed_bytes", data)

    def test_cleaner_clean_api_with_password(self):
        url = f"http://127.0.0.1:{self.port}/api/cleaner/clean"
        body = json.dumps({"targets": ["pacman"], "password": "wrongpassword123"}).encode('utf-8')
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=5) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("results", data)
            pacman_res = next((r for r in data["results"] if r["id"] == "pacman"), None)
            self.assertIsNotNone(pacman_res)
            self.assertFalse(pacman_res["success"])
            self.assertIsNotNone(pacman_res.get("error"))

