import os
import stat
import tempfile
import unittest
from pathlib import Path

from targz_manager.dotfiles_manager import DotfilesManager


class TestDotfilesManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)

        # Create mock packages
        (self.repo_dir / "home").mkdir()
        (self.repo_dir / "config").mkdir()

        # Create mock script
        self.script_path = self.repo_dir / "dotfiles"
        self.script_path.write_text(
            "#!/bin/sh\n"
            "cmd=\"$1\"\n"
            "case \"$cmd\" in\n"
            "  check) echo \"Stow check passed\";;\n"
            "  apply) echo \"Stow applied\";;\n"
            "  status) echo \"On branch main\nnothing to commit\";;\n"
            "  save) echo \"Saved commit: $2\";;\n"
            "  *) echo \"Unknown command $cmd\"; exit 1;;\n"
            "esac\n"
        )
        self.script_path.chmod(self.script_path.stat().st_mode | stat.S_IEXEC)

        self.mgr = DotfilesManager(repo_dir=self.repo_dir)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_get_status(self):
        status = self.mgr.get_status()
        self.assertTrue(status["exists"])
        self.assertTrue(status["has_script"])
        pkg_names = [p["name"] for p in status["packages"]]
        self.assertIn("home", pkg_names)
        self.assertIn("config", pkg_names)

    def test_is_package_stowed(self):
        target_dir = Path(self.temp_dir.name) / "home_target"
        target_dir.mkdir()
        self.mgr.target_dir = target_dir

        # Create a file inside home package
        test_file = self.repo_dir / "home" / "test_file.txt"
        test_file.write_text("hello")

        # Before symlinking, should not be stowed
        self.assertFalse(self.mgr.is_package_stowed("home"))

        # Symlink into target
        (target_dir / "test_file.txt").symlink_to(test_file)
        self.assertTrue(self.mgr.is_package_stowed("home"))

    def test_selective_stow_requires_package(self):
        res = self.mgr.run_command("stow")
        self.assertFalse(res["success"])
        self.assertIn("required", res["error"].lower())

    def test_run_allowed_commands(self):
        res = self.mgr.run_command("check")
        self.assertTrue(res["success"])
        self.assertIn("Stow check passed", res["output"])

        res_apply = self.mgr.run_command("apply")
        self.assertTrue(res_apply["success"])
        self.assertIn("Stow applied", res_apply["output"])

        res_save = self.mgr.run_command("save", message="my test commit")
        self.assertTrue(res_save["success"])
        self.assertIn("Saved commit: my test commit", res_save["output"])

    def test_disallow_unsafe_command(self):
        res = self.mgr.run_command("rm -rf /")
        self.assertFalse(res["success"])
        self.assertIn("not allowed", res["error"].lower())


class TestDotfilesHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        import urllib.request
        from targz_manager.db import Database
        from targz_manager.installer import Installer
        from targz_manager.server import create_server
        import threading

        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.temp_dir.name) / "test.db"
        db = Database(db_path)
        installer = Installer(db)
        cls.server = create_server(host="127.0.0.1", port=0, installer=installer)
        cls.port = cls.server.server_address[1]

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.temp_dir.cleanup()

    def test_dotfiles_status_api(self):
        import urllib.request
        import json
        url = f"http://127.0.0.1:{self.port}/api/dotfiles/status"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("exists", data)
            self.assertIn("packages", data)
            self.assertIn("git", data)


    def test_dotfiles_run_api(self):
        import urllib.request
        import json
        url = f"http://127.0.0.1:{self.port}/api/dotfiles/run"
        payload = json.dumps({"command": "status"}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("command", data)


if __name__ == "__main__":
    unittest.main()
