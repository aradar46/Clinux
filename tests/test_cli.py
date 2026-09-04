import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock

from clinux.cli import run_cli, print_cli_table


class TestCLI(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="clinux_cli_test_"))
        self.db_file = self.temp_dir / "test.db"

    def test_list_command_json(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = run_cli(["--db", str(self.db_file), "list", "--json"])
        self.assertEqual(ret, 0)
        output = json.loads(stdout.getvalue())
        self.assertIn("apps", output)

    def test_disk_command_json(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = run_cli(["--db", str(self.db_file), "disk", "--json"])
        self.assertEqual(ret, 0)
        output = json.loads(stdout.getvalue())
        self.assertIn("disk", output)

    def test_clean_dry_run_json(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = run_cli(["--db", str(self.db_file), "clean", "--dry-run", "--json"])
        self.assertEqual(ret, 0)
        output = json.loads(stdout.getvalue())
        self.assertIn("targets", output)

    @patch("clinux.modules.skills.SkillsModule.scan")
    def test_skills_command_json(self, mock_scan):
        mock_scan.return_value = {"skills": [], "categories": []}
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = run_cli(["--db", str(self.db_file), "skills", "--json"])
        self.assertEqual(ret, 0)
        output = json.loads(stdout.getvalue())
        self.assertIn("skills", output)

    def test_ai_storage_command_json(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            ret = run_cli(["--db", str(self.db_file), "ai-storage", "--json"])
        self.assertEqual(ret, 0)
        output = json.loads(stdout.getvalue())
        self.assertIn("models", output)

    def test_print_cli_table_empty(self):
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            print_cli_table([])
        self.assertIn("No applications are currently managed", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
