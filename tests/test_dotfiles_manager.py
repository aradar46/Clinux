import os
import stat
import tempfile
import unittest
import subprocess
from pathlib import Path

from core.dotfiles_manager import DotfilesManager
from core.db import Database


class TestDotfilesManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.repo_dir = Path(self.temp_dir.name)
        self.root_dir = Path(self.temp_dir.name)
        self.repo_dir = self.root_dir / "dotfiles"
        self.repo_dir.mkdir()
        self.target_dir = self.root_dir / "target_home"
        self.target_dir.mkdir()

        # Create mock packages
        (self.repo_dir / "home").mkdir()
        (self.repo_dir / "config").mkdir()
        (self.repo_dir / "zsh").mkdir()
        (self.repo_dir / "nvim").mkdir()

        # Create mock script
        # Create mock script for backward-compatibility test
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
        db_path = self.root_dir / "test.db"
        self.db = Database(db_path)
        self.mgr = DotfilesManager(repo_dir=self.repo_dir, target_dir=self.target_dir, db=self.db)

    def tearDown(self):
        self.db.close()
        self.temp_dir.cleanup()
    def test_set_paths_and_persistence(self):
        new_repo = self.root_dir / "custom_dotfiles"
        new_repo.mkdir()
        res = self.mgr.set_paths(repo_dir=new_repo, persist=True)
        self.assertTrue(res["success"])
        self.assertEqual(str(self.mgr.repo_dir), str(new_repo.resolve()))

        # Check persistence in DB
        opts = self.db.get_options()
        self.assertEqual(opts.get("dotfiles", {}).get("repo_path"), str(new_repo.resolve()))

    def test_get_status_structure(self):
        status = self.mgr.get_status()
        self.assertTrue(status["exists"])
        self.assertTrue(status["has_script"])
        self.assertIn("stow_installed", status)
        self.assertIn("git_installed", status)
        self.assertIn("packages", status)
        self.assertIn("git", status)

        pkg_names = [p["name"] for p in status["packages"]]
        self.assertIn("home", pkg_names)
        self.assertIn("config", pkg_names)
        self.assertIn("zsh", pkg_names)
        self.assertIn("nvim", pkg_names)

    def test_is_package_stowed(self):
        test_file = self.repo_dir / "home" / "test_file.txt"
        test_file.write_text("hello")
        self.assertFalse(self.mgr.is_package_stowed("home"))
        (self.target_dir / "test_file.txt").symlink_to(test_file)
        self.assertTrue(self.mgr.is_package_stowed("home"))

    def test_package_stow_status_detection(self):
        # Empty package
        status_empty = self.mgr.get_package_stow_status("zsh")
        self.assertEqual(status_empty["status"], "empty")

        # Add files to zsh package
        test_file = self.repo_dir / "zsh" / ".zshrc"
        test_file.write_text("export FOO=1")

        # Before symlinking -> unstowed
        status_unstowed = self.mgr.get_package_stow_status("zsh")
        self.assertEqual(status_unstowed["status"], "unstowed")
        self.assertFalse(status_unstowed["stowed"])

        # After symlinking direct file -> stowed
        target_link = self.target_dir / ".zshrc"
        target_link.symlink_to(test_file)
        status_stowed = self.mgr.get_package_stow_status("zsh")
        self.assertEqual(status_stowed["status"], "stowed")
        self.assertTrue(status_stowed["stowed"])

    def test_selective_stow_requires_package(self):
        res = self.mgr.run_command("stow")
        self.assertFalse(res["success"])
        self.assertIn("required", res["error"].lower())

    def test_selective_stow_rejects_path_traversal(self):
        res = self.mgr.run_command("stow", package="../../etc")
        self.assertFalse(res["success"])
        self.assertIn("not allowed", res["error"].lower())

    def test_folded_directory_stow_detection(self):
        # Nested file inside package
        cfg_dir = self.repo_dir / "nvim" / ".config" / "nvim"
        cfg_dir.mkdir(parents=True)
        init_lua = cfg_dir / "init.lua"
        init_lua.write_text("print('hello')")

        # Folded directory symlink in target (.config/nvim -> dotfiles/nvim/.config/nvim)
        target_cfg_parent = self.target_dir / ".config"
        target_cfg_parent.mkdir(parents=True)
        (target_cfg_parent / "nvim").symlink_to(cfg_dir)

        status = self.mgr.get_package_stow_status("nvim")
        self.assertEqual(status["status"], "stowed")
        self.assertTrue(status["stowed"])

    def test_run_stow_validation(self):
        # Disallow path traversal
        res_trav = self.mgr.run_stow(action="stow", package="../../etc")
        self.assertFalse(res_trav["success"])
        self.assertIn("traversal", res_trav["error"].lower())

        # Disallow hidden dirs as packages
        res_dot = self.mgr.run_stow(action="stow", package=".git")
        self.assertFalse(res_dot["success"])
        self.assertIn("hidden", res_dot["error"].lower())

        # Nonexistent package
        res_non = self.mgr.run_stow(action="stow", package="nonexistent_pkg_123")
        self.assertFalse(res_non["success"])
        self.assertIn("not found", res_non["error"].lower())

    def test_run_stow_simulate(self):
        # Add file
        (self.repo_dir / "zsh" / ".zshrc").write_text("# zsh")
        if self.mgr.is_stow_installed():
            res = self.mgr.run_stow(action="stow", package="zsh", simulate=True)
            self.assertTrue(res["success"])
            self.assertIn("-n", res["command"])
            # Because simulate, target file should not actually exist
            self.assertFalse((self.target_dir / ".zshrc").exists())

    def test_git_operations(self):
        # Non-git repo initially
        info = self.mgr.get_git_info()
        self.assertFalse(info["is_git"])

        res_pull = self.mgr.run_git("pull")
        self.assertFalse(res_pull["success"])
        self.assertIn("not a git repository", res_pull["error"].lower())

        # Initialize git repo
        res_init = self.mgr.run_git("init")
        self.assertTrue(res_init["success"])

        # Configure dummy git user
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(self.repo_dir), check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(self.repo_dir), check=True)

        # Commit changes
        res_commit = self.mgr.run_git("commit", message="Initial commit")
        self.assertTrue(res_commit["success"])

        # Check git info
        git_info = self.mgr.get_git_info()
        self.assertTrue(git_info["is_git"])
        self.assertTrue(git_info["clean"])

        # Test force flag in push command construction
        # Note: push without remote will exit with error from git, but command will contain --force-with-lease
        res_push = self.mgr.run_git("push", force=True)
        self.assertIn("--force-with-lease", res_push["command"])

    def test_run_command_compatibility(self):
        # Legacy script dispatcher check
        res = self.mgr.run_command("check")
        self.assertTrue(res["success"])
        self.assertIn("Stow check passed", res["output"])

        res_apply = self.mgr.run_command("apply")
        self.assertTrue(res_apply["success"])
        self.assertIn("Stow applied", res_apply["output"])

        res_save = self.mgr.run_command("save", message="my test commit")
        self.assertTrue(res_save["success"])
        self.assertIn("Saved commit: my test commit", res_save["output"])
        # Disallowed unsafe command
        res_bad = self.mgr.run_command("rm -rf /")
        self.assertFalse(res_bad["success"])

    def test_disallow_unsafe_command(self):
        res = self.mgr.run_command("rm -rf /")
        self.assertFalse(res["success"])
        self.assertIn("not allowed", res["error"].lower())


class TestDotfilesHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        import json
        import urllib.request
        from core.db import Database
        from core.installer import Installer
        from core.server import create_server
        import threading

        cls.temp_dir = tempfile.TemporaryDirectory()
        db_path = Path(cls.temp_dir.name) / "test.db"
        db = Database(db_path)
        installer = Installer(db)
        cls.server = create_server(host="127.0.0.1", port=0, installer=installer)
        cls.db = Database(db_path)
        cls.installer = Installer(cls.db)
        cls.server = create_server(host="127.0.0.1", port=0, installer=cls.installer)
        cls.port = cls.server.server_address[1]

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.db.close()
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
            self.assertIn("stow_installed", data)

    def test_dotfiles_config_api(self):
        import urllib.request
        import json

        url = f"http://127.0.0.1:{self.port}/api/dotfiles/config"
        new_repo = str(Path(self.temp_dir.name) / "my_dotfiles")
        payload = json.dumps({"repo_path": new_repo, "persist": True}).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data["success"])
            self.assertEqual(data["repo_path"], str(Path(new_repo).resolve()))

    def test_dotfiles_stow_api(self):
        import urllib.request
        import json

        url = f"http://127.0.0.1:{self.port}/api/dotfiles/stow"
        payload = json.dumps({
            "action": "stow",
            "package": "test_package",
            "simulate": True
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("success", data)
            self.assertIn("command", data)

    def test_dotfiles_git_api(self):
        import urllib.request
        import json

        url = f"http://127.0.0.1:{self.port}/api/dotfiles/git"
        payload = json.dumps({
            "action": "status",
            "force": False
        }).encode("utf-8")
        req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("success", data)
            self.assertIn("action", data)

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
