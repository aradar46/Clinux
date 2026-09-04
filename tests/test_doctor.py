import os
import tempfile
import unittest
from unittest import mock
from targz_manager.doctor import SystemDoctor

class TestSystemDoctor(unittest.TestCase):
    def setUp(self):
        self.doctor = SystemDoctor()

    def test_fix_broken_desktop_entry(self):
        with tempfile.NamedTemporaryFile(delete=False) as tf:
            tf.write(b"[Desktop Entry]\nExec=nonexistent_app_xyz")
            file_path = tf.name

        self.assertTrue(os.path.exists(file_path))
        problem = {
            "type": "broken_desktop_entry",
            "path": file_path,
            "fix_command": f"rm '{file_path}'"
        }

        res = self.doctor.fix(problem)
        self.assertTrue(res)
        self.assertFalse(os.path.exists(file_path))

    def test_fix_no_command(self):
        problem = {
            "type": "failed_service",
            "fix_command": None
        }
        res = self.doctor.fix(problem)
        self.assertFalse(res)

    def test_fix_command_execution(self):
        with mock.patch("subprocess.run") as mock_run:
            mock_run.return_value.returncode = 0
            problem = {
                "type": "failed_service",
                "fix_command": "sudo systemctl restart failed.service"
            }
            res = self.doctor.fix(problem)
            self.assertTrue(res)
            mock_run.assert_called_once_with(["sudo", "systemctl", "restart", "failed.service"], capture_output=True, text=True, check=True)

    def test_fix_command_injection_prevention(self):
        test_canary = os.path.join(tempfile.gettempdir(), "doctor_injection_canary.txt")
        if os.path.exists(test_canary):
            os.remove(test_canary)

        problem = {
            "type": "network",
            "fix_command": f"echo hello ; touch {test_canary}"
        }

        # Should fail as 'echo' will receive ';', 'touch', and canary file path as literal arguments rather than executing shell command chaining
        res = self.doctor.fix(problem)
        self.assertFalse(os.path.exists(test_canary))

if __name__ == "__main__":
    unittest.main()
