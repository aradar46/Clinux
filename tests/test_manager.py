import os
import sys
import json
import time
import shutil
import tempfile
import unittest
import urllib.request
import urllib.error
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from targz_manager.db import Database
from targz_manager.installer import Installer, ArchiveError
from targz_manager.server import create_server


class TestTarGzManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="targz_test_"))
        self.db_path = self.temp_dir / "test_apps.db"
        self.db = Database(self.db_path)
        self.installer = Installer(self.db)

        # Create dummy archives for testing
        self.sample_app_dir = self.temp_dir / "sample-app-1.0.0"
        self.sample_app_dir.mkdir()
        (self.sample_app_dir / "bin").mkdir()
        
        # Executable binary / script
        exec_file = self.sample_app_dir / "bin" / "sampleapp"
        with open(exec_file, "w") as f:
            f.write("#!/bin/sh\necho 'Running sampleapp v1.0.0'\n")
        exec_file.chmod(0o755)

        # Dummy icon
        icon_file = self.sample_app_dir / "icon.png"
        with open(icon_file, "wb") as f:
            f.write(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15c4\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82")

        # Package into tar.gz
        self.tar_gz_path = self.temp_dir / "sample-app-1.0.0-linux-x64.tar.gz"
        shutil.make_archive(
            str(self.temp_dir / "sample-app-1.0.0-linux-x64"),
            "gztar",
            root_dir=str(self.temp_dir),
            base_dir="sample-app-1.0.0"
        )

        # Create version 2.0.0 tar.gz for update test
        self.sample_app_v2 = self.temp_dir / "sample-app-2.0.0"
        self.sample_app_v2.mkdir()
        (self.sample_app_v2 / "bin").mkdir()
        v2_exec = self.sample_app_v2 / "bin" / "sampleapp"
        with open(v2_exec, "w") as f:
            f.write("#!/bin/sh\necho 'Running sampleapp v2.0.0'\n")
        v2_exec.chmod(0o755)

        self.tar_gz_v2_path = self.temp_dir / "sample-app-2.0.0-linux-x64.tar.gz"
        shutil.make_archive(
            str(self.temp_dir / "sample-app-2.0.0-linux-x64"),
            "gztar",
            root_dir=str(self.temp_dir),
            base_dir="sample-app-2.0.0"
        )

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_crud_and_stats(self):
        # Initial empty
        self.assertEqual(len(self.db.list_apps()), 0)

        # Add app
        app_id = self.db.add_app({
            "name": "test-app",
            "display_name": "Test Application",
            "version": "1.0.0",
            "category": "Development",
            "install_path": str(self.temp_dir / "installed" / "test-app"),
            "executable_path": str(self.temp_dir / "installed" / "test-app" / "bin" / "testapp"),
            "size_bytes": 1024 * 1024 * 10, # 10 MB
        })
        self.assertTrue(app_id > 0)

        # Read app
        app = self.db.get_app(app_id)
        self.assertEqual(app["name"], "test-app")
        self.assertEqual(app["display_name"], "Test Application")
        self.assertEqual(app["version"], "1.0.0")

        # Update app
        updated = self.db.update_app(app_id, {"version": "1.1.0", "display_name": "Test App Updated"})
        self.assertTrue(updated)
        app = self.db.get_app(app_id)
        self.assertEqual(app["version"], "1.1.0")
        self.assertEqual(app["display_name"], "Test App Updated")

        # Stats
        stats = self.db.get_stats()
        self.assertEqual(stats["total_apps"], 1)
        self.assertIn("Development", stats["categories"])

        # Delete app
        deleted = self.db.delete_app(app_id)
        self.assertTrue(deleted)
        self.assertEqual(len(self.db.list_apps()), 0)

    def test_inspect_archive(self):
        info = self.installer.inspect_archive(str(self.tar_gz_path))
        self.assertEqual(info["guessed_name"], "sample-app")
        self.assertEqual(info["guessed_version"], "1.0.0")
        self.assertTrue(info["has_wrapper_folder"])
        self.assertEqual(info["wrapper_folder"], "sample-app-1.0.0")
        self.assertTrue(len(info["executables"]) >= 1)
        self.assertEqual(info["executables"][0]["path"], "bin/sampleapp")
        self.assertTrue(len(info["icons"]) >= 1)

    def test_install_update_and_uninstall_lifecycle(self):
        dest_path = self.temp_dir / "opt" / "sample-app"

        # 1. Install
        app = self.installer.install_app(
            archive_path=str(self.tar_gz_path),
            name="sample-app",
            display_name="Sample App",
            version="1.0.0",
            category="Utility",
            install_path=str(dest_path),
            create_desktop=True,
            create_bin_symlink=True,
            flatten_wrapper=True
        )

        self.assertTrue(dest_path.exists())
        self.assertTrue((dest_path / "bin" / "sampleapp").exists())
        self.assertTrue(Path(app["executable_path"]).exists())
        self.assertTrue(Path(app["desktop_entry_path"]).exists())
        self.assertTrue(Path(app["symlink_path"]).exists())

        # 2. Update to v2.0.0
        updated_app = self.installer.update_app(
            app_id=app["id"],
            archive_path=str(self.tar_gz_v2_path),
            new_version="2.0.0",
            flatten_wrapper=True
        )
        self.assertEqual(updated_app["version"], "2.0.0")
        self.assertTrue(dest_path.exists())
        self.assertTrue((dest_path / "bin" / "sampleapp").exists())

        # Check content of updated executable
        with open(dest_path / "bin" / "sampleapp", "r") as f:
            content = f.read()
        self.assertIn("v2.0.0", content)

        # 3. Uninstall
        uninst_res = self.installer.uninstall_app(
            app_id=app["id"],
            delete_files=True,
            delete_desktop=True,
            delete_symlink=True
        )
        self.assertTrue(uninst_res["success"])
        self.assertFalse(dest_path.exists())
        self.assertFalse(Path(app["desktop_entry_path"]).exists())
        self.assertFalse(Path(app["symlink_path"]).exists())
        self.assertIsNone(self.db.get_app(app["id"]))

    def test_register_existing_app(self):
        # Register a folder that is already on disk
        app = self.installer.register_existing_app(
            name="existing-app",
            display_name="Existing App",
            install_path=str(self.sample_app_dir),
            executable_path=str(self.sample_app_dir / "bin" / "sampleapp"),
            version="1.0.0",
            category="Development",
            create_desktop=True,
            create_bin_symlink=True
        )

        self.assertEqual(app["source_type"], "registered")
        self.assertTrue(Path(app["desktop_entry_path"]).exists())
        self.assertTrue(Path(app["symlink_path"]).exists())

        # Clean up registered app
        self.installer.uninstall_app(
            app_id=app["id"],
            delete_files=False, # Keep original files
            delete_desktop=True,
            delete_symlink=True
        )
        self.assertTrue(self.sample_app_dir.exists())
    def test_scanner_auto_resolve_and_discovery(self):
        from targz_manager.scanner import SystemScanner
        scanner = SystemScanner(self.db, self.installer)

        # Test auto resolve directory
        resolved = scanner.auto_resolve_directory(str(self.sample_app_dir))
        self.assertEqual(resolved["name"], "sample-app")
        self.assertEqual(resolved["version"], "1.0.0")
        self.assertTrue(resolved["executable_path"].endswith("sampleapp"))
        self.assertTrue(resolved["icon_path"].endswith("icon.png"))

        # Test discover
        discovered = scanner.discover_unmanaged_apps()
        self.assertTrue(isinstance(discovered, list))


class TestHttpServerApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="targz_server_test_"))
        cls.db_path = cls.temp_dir / "api_test.db"
        cls.db = Database(cls.db_path)
        cls.installer = Installer(cls.db)
        
        cls.port = 8499
        cls.server = create_server(host="127.0.0.1", port=cls.port, installer=cls.installer)
        
        import threading
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()
        time.sleep(0.1)

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_get_index_html(self):
        url = f"http://127.0.0.1:{self.port}/"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            content = resp.read().decode('utf-8')
            self.assertIn("TarGz Manager", content)
            self.assertIn("Install Tarball", content)

    def test_get_stats_and_system_info(self):
        # Stats
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/stats") as resp:
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("stats", data)
            self.assertEqual(data["stats"]["total_apps"], 0)

        # System info
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/system-info") as resp:
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("home", data)
            self.assertIn("opt_dir", data)

    def test_get_discovered_api(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/discovered") as resp:
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("discovered", data)
            self.assertTrue(isinstance(data["discovered"], list))

    def test_filesystem_browse_api(self):
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/browse?path={str(Path.home())}") as resp:
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("current_path", data)
            self.assertIn("quick_links", data)
            self.assertIn("items", data)


if __name__ == "__main__":
    unittest.main()
