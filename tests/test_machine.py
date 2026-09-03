import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

PROJECT_ROOT = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(PROJECT_ROOT))

from targz_manager.db import Database
from targz_manager.machine import MachineManager


class TestMachineManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="machine_test_"))
        self.db_path = self.temp_dir / "test_apps.db"
        self.db = Database(self.db_path)
        self.machine_mgr = MachineManager(self.db)

    def tearDown(self):
        import shutil
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_parse_toml(self):
        sample_toml = """
# Sample comment
[dotfiles]
repo = "/home/user/.dotfiles"
packages = ['vim', 'zsh']

[git_config]
"user.name" = "Test User"
"user.email" = "test@example.com"

[[portable_apps]]
name = "app1"
display_name = "App One"
version = "1.0.0"

[[portable_apps]]
name = "app2"
display_name = "App Two"
version = "2.0.0"

[python]
versions = ['3.10.0', '3.11.0']

[gnome_settings]
dconf = \"\"\"
[org/gnome/desktop]
theme='Adwaita'
\"\"\"
"""
        parsed = self.machine_mgr._parse_toml(sample_toml)
        self.assertEqual(parsed["dotfiles"]["repo"], "/home/user/.dotfiles")
        self.assertEqual(parsed["dotfiles"]["packages"], ['vim', 'zsh'])
        self.assertEqual(parsed["git_config"]["user.name"], "Test User")
        self.assertEqual(parsed["git_config"]["user.email"], "test@example.com")

        self.assertEqual(len(parsed["portable_apps"]), 2)
        self.assertEqual(parsed["portable_apps"][0]["name"], "app1")
        self.assertEqual(parsed["portable_apps"][1]["version"], "2.0.0")

        self.assertEqual(parsed["python"]["versions"], ['3.10.0', '3.11.0'])
        self.assertIn("Adwaita", parsed["gnome_settings"]["dconf"])

    def test_collect_portable_apps(self):
        self.db.add_app({
            "name": "sample-app",
            "display_name": "Sample App",
            "version": "1.0.0",
            "category": "Utility",
            "install_path": "/opt/sample",
            "executable_path": "/opt/sample/bin/sample"
        })
        apps = self.machine_mgr._collect_portable_apps()
        self.assertEqual(len(apps), 1)
        self.assertEqual(apps[0]["name"], "sample-app")
        self.assertEqual(apps[0]["display_name"], "Sample App")
        self.assertEqual(apps[0]["version"], "1.0.0")

    @mock.patch("targz_manager.machine.subprocess.run")
    def test_collect_git_config(self, mock_run):
        mock_proc = mock.MagicMock()
        mock_proc.stdout = "user.name=Jane Doe\nuser.email=jane@example.com\n"
        mock_run.return_value = mock_proc

        git_cfg = self.machine_mgr._collect_git_config()
        self.assertEqual(git_cfg.get("user.name"), "Jane Doe")
        self.assertEqual(git_cfg.get("user.email"), "jane@example.com")

    @mock.patch("targz_manager.machine.subprocess.run")
    def test_collect_package_info(self, mock_run):
        def side_effect(cmd, capture_output, text):
            proc = mock.MagicMock()
            if cmd[0] == "apt-mark":
                proc.returncode = 0
                proc.stdout = "curl\ngit\n"
            elif cmd[0] == "pacman":
                proc.returncode = 0
                proc.stdout = "htop\nneofetch\n"
            else:
                proc.returncode = 1
                proc.stdout = ""
            return proc

        mock_run.side_effect = side_effect

        pkg_info = self.machine_mgr._collect_package_info()
        self.assertEqual(pkg_info["apt"], ["curl", "git"])
        self.assertEqual(pkg_info["pacman"], ["htop", "neofetch"])

    @mock.patch("targz_manager.machine.subprocess.run")
    def test_collect_python_versions(self, mock_run):
        mock_proc = mock.MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "3.10.4\n3.11.2\n"
        mock_run.return_value = mock_proc

        py_vers = self.machine_mgr._collect_python_versions()
        self.assertEqual(py_vers, ["3.10.4", "3.11.2"])

    @mock.patch("targz_manager.machine.subprocess.run")
    def test_collect_node_versions(self, mock_run):
        mock_proc = mock.MagicMock()
        mock_proc.returncode = 0
        mock_proc.stdout = "v18.16.0\n"
        mock_run.return_value = mock_proc

        node_vers = self.machine_mgr._collect_node_versions()
        self.assertEqual(node_vers, ["v18.16.0"])

    def test_format_manifest_toml(self):
        data = {
            "dotfiles": {"repo_path": "/home/user/dotfiles", "stowed_packages": ["bash", "zsh"]},
            "git_config": {"user.name": "John Doe"},
            "packages": {"apt": ["curl"], "pacman": []},
            "portable_apps": [{"name": "app1", "display_name": "App 1", "version": "1.0"}],
            "python": {"versions": ["3.11.0"]},
            "node": {"versions": ["v18.0.0"]},
            "ai_skills": {"active": ["skill1"]},
            "gnome_settings": {"dconf": "[org/gnome]\nkey='val'"},
        }
        toml_out = self.machine_mgr._format_manifest_toml(data)
        self.assertIn('[dotfiles]', toml_out)
        self.assertIn('repo = "/home/user/dotfiles"', toml_out)
        self.assertIn('[git_config]', toml_out)
        self.assertIn('"user.name" = "John Doe"', toml_out)
        self.assertIn('apt = [\'curl\']', toml_out)
        self.assertIn('[[portable_apps]]', toml_out)
        self.assertIn('versions = [\'3.11.0\']', toml_out)
        self.assertIn('active = [\'skill1\']', toml_out)

    def test_export_and_restore_machine_flow(self):
        output_file = str(self.temp_dir / "machine_manifest.toml")

        # Mock sub-calls for predictable export
        with mock.patch.object(self.machine_mgr, "_collect_dotfiles_info", return_value={"repo_path": "/tmp/dot", "stowed_packages": ["vim"]}):
            with mock.patch.object(self.machine_mgr, "_collect_git_config", return_value={"user.name": "Tester"}):
                with mock.patch.object(self.machine_mgr, "_collect_package_info", return_value={"apt": ["wget"], "pacman": []}):
                    with mock.patch.object(self.machine_mgr, "_collect_portable_apps", return_value=[]):
                        with mock.patch.object(self.machine_mgr, "_collect_python_versions", return_value=["3.11.0"]):
                            with mock.patch.object(self.machine_mgr, "_collect_node_versions", return_value=["v20.0.0"]):
                                with mock.patch.object(self.machine_mgr, "_collect_ai_skills", return_value=[]):
                                    with mock.patch.object(self.machine_mgr, "_collect_gnome_settings", return_value=""):
                                        exported_path = self.machine_mgr.export_machine(output_file)
                                        self.assertEqual(exported_path, output_file)
                                        self.assertTrue(os.path.exists(output_file))

        # Restore from the exported manifest
        with mock.patch.object(self.machine_mgr.dm, "run_command", return_value={"success": True}):
            with mock.patch("targz_manager.machine.subprocess.run") as mock_sub_run:
                mock_sub_run.return_value = mock.MagicMock(returncode=0)
                restore_res = self.machine_mgr.restore_machine(output_file)

                self.assertTrue(any("Dotfiles:" in line for line in restore_res))
                self.assertTrue(any("Git:" in line for line in restore_res))
                self.assertTrue(any("APT:" in line for line in restore_res))
                self.assertTrue(any("Python:" in line for line in restore_res))

    def test_restore_machine_nonexistent_file(self):
        res = self.machine_mgr.restore_machine("/path/does/not/exist.toml")
        self.assertEqual(len(res), 1)
        self.assertIn("Error: Manifest file", res[0])


if __name__ == "__main__":
    unittest.main()
