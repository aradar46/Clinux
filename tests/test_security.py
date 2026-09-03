import os
import tempfile
import unittest
from pathlib import Path

from targz_manager.security import SecurityAuditor


class TestSecurityAuditor(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.home_path = Path(self.temp_dir.name)
        self.auditor = SecurityAuditor(home_dir=self.home_path)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_audit_all_returns_structure(self):
        res = self.auditor.audit_all()
        self.assertIn("timestamp", res)
        self.assertIn("user", res)
        self.assertIn("summary", res)
        self.assertIn("findings", res)
        self.assertIsInstance(res["findings"], list)

    def test_ssh_directory_checks(self):
        ssh_dir = self.home_path / ".ssh"
        ssh_dir.mkdir(mode=0o777)
        priv_key = ssh_dir / "id_ed25519"
        priv_key.write_text("dummy key")
        priv_key.chmod(0o644)

        findings = self.auditor.check_ssh_configuration()
        high_findings = [f for f in findings if f["severity"] == "HIGH"]
        self.assertTrue(any("Directory Permissions" in f["title"] or "Private Key" in f["title"] for f in high_findings))

    def test_env_secrets_check(self):
        proj_dir = self.home_path / "projects" / "testapp"
        proj_dir.mkdir(parents=True)
        env_file = proj_dir / ".env"
        env_file.write_text("AWS_SECRET_ACCESS_KEY=1234567890abcdef1234\nAPI_KEY=secret_key_1234567890")

        findings = self.auditor.check_env_and_private_keys()
        env_finding = next((f for f in findings if f["id"] == "env_file_secrets"), None)
        self.assertIsNotNone(env_finding)
        self.assertEqual(env_finding["severity"], "HIGH")

    def test_report_text_formatting_and_export(self):
        audit_res = self.auditor.audit_all()
        text_rep = self.auditor.format_text_report(audit_res)
        self.assertIn("CLINUX SECURITY AUDIT", text_rep)
        self.assertIn("HIGH", text_rep)

        saved = self.auditor.export_report(audit_res, format_type="text")
        export_p = Path(saved)
        self.assertTrue(Path(saved).exists())
        self.assertEqual(export_p.parent, self.home_path)
        self.assertIn("CLINUX SECURITY AUDIT", export_p.read_text())

    def test_export_rejects_path_outside_home(self):
        audit_res = self.auditor.audit_all()
        with self.assertRaises(ValueError):
            self.auditor.export_report(audit_res, filepath="/tmp/clinux-report.txt", format_type="text")


if __name__ == "__main__":
    unittest.main()
