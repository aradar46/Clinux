import os
import shutil
import tempfile
import unittest
from pathlib import Path

from targz_manager.ai_manager import SkillManager, AIStorageManager, AIRuntimeDetector


class TestAIManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        # Mock skills repo layout:
        # base_path / repo / science / literature-review / SKILL.md
        # base_path / repo / developer-utilities / caveman / SKILL.md
        self.repo_dir = self.base_path / "repo"
        lit_dir = self.repo_dir / "science" / "literature-review"
        lit_dir.mkdir(parents=True)
        (lit_dir / "SKILL.md").write_text(
            "---\nname: literature-review\ndescription: Conduct systematic literature reviews\n---\n# Literature Review\n"
        )

        caveman_dir = self.repo_dir / "developer-utilities" / "caveman"
        caveman_dir.mkdir(parents=True)
        (caveman_dir / "SKILL.md").write_text(
            "---\nname: caveman\ndescription: Terse agent responses\n---\n# Caveman\n"
        )

        # Mock agent targets
        self.claude_skills = self.base_path / "claude_skills"
        self.claude_skills.mkdir(parents=True)
        self.agy_skills = self.claude_skills / "Agy"
        self.agy_skills.mkdir(parents=True)
        self.codex_skills = self.base_path / "codex_skills"
        self.codex_skills.mkdir(parents=True)

        self.targets = {
            "claude": self.claude_skills,
            "agy": self.agy_skills,
            "codex": self.codex_skills,
        }

        self.manager = SkillManager(repo_dirs=[self.repo_dir], target_dirs=self.targets)

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_discover_skills(self):
        skills = self.manager.get_all_skills()
        self.assertEqual(len(skills), 2)
        names = {s["name"] for s in skills}
        self.assertIn("literature-review", names)
        self.assertIn("caveman", names)

        lit = next(s for s in skills if s["name"] == "literature-review")
        self.assertEqual(lit["category"], "science")
        self.assertEqual(lit["description"], "Conduct systematic literature reviews")

    def test_activate_and_deactivate_skill(self):
        # Initially not active
        status = self.manager.get_skill_status("science/literature-review")
        self.assertFalse(status["active"])

        # Activate for claude and agy
        res = self.manager.activate_skill("science/literature-review", targets=["claude", "agy"])
        self.assertTrue(res["success"])

        # Check symlinks exist
        claude_link = self.claude_skills / "literature-review"
        agy_link = self.agy_skills / "literature-review"
        codex_link = self.codex_skills / "literature-review"

        self.assertTrue(claude_link.is_symlink())
        self.assertTrue(agy_link.is_symlink())
        self.assertFalse(codex_link.exists())

        status = self.manager.get_skill_status("science/literature-review")
        self.assertTrue(status["active"])
        self.assertTrue(status["active_targets"]["claude"])
        self.assertTrue(status["active_targets"]["agy"])
        self.assertFalse(status["active_targets"]["codex"])

        # Deactivate
        deact = self.manager.deactivate_skill("science/literature-review", targets=["claude", "agy"])
        self.assertTrue(deact["success"])
        self.assertFalse(claude_link.exists())
        self.assertFalse(agy_link.exists())

    def test_protect_real_directory(self):
        # Create real directory with same name in target
        real_dir = self.claude_skills / "caveman"
        real_dir.mkdir()
        (real_dir / "keep_me.txt").write_text("critical data")

        # Deactivating should refuse to delete real directory
        res = self.manager.deactivate_skill("developer-utilities/caveman", targets=["claude"])
        self.assertTrue(real_dir.exists())
        self.assertTrue((real_dir / "keep_me.txt").exists())

    def test_category_toggle(self):
        # Activate entire science category
        res = self.manager.toggle_category("science", active=True, targets=["claude", "agy"])
        self.assertTrue(res["success"])
        claude_link = self.claude_skills / "literature-review"
        self.assertTrue(claude_link.is_symlink())

        # Deactivate entire science category
        res_deact = self.manager.toggle_category("science", active=False, targets=["claude", "agy"])
        self.assertTrue(res_deact["success"])
        self.assertFalse(claude_link.exists())


class TestAIStorageManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.base_path = Path(self.temp_dir.name)

        # Mock Hugging Face cache
        self.hf_dir = self.base_path / "cache" / "huggingface" / "hub"
        model1 = self.hf_dir / "models--bert-base-uncased"
        model1.mkdir(parents=True)
        (model1 / "pytorch_model.bin").write_bytes(b"X" * 1024 * 50)  # 50 KB

        # Mock PyTorch checkpoints
        self.torch_dir = self.base_path / "cache" / "torch" / "hub" / "checkpoints"
        self.torch_dir.mkdir(parents=True)
        (self.torch_dir / "resnet50.pth").write_bytes(b"Y" * 1024 * 25)  # 25 KB

        # Mock Claude Code workspace
        self.claude_projects = self.base_path / "claude" / "projects"
        self.claude_projects.mkdir(parents=True)
        (self.claude_projects / "history.jsonl").write_bytes(b"Z" * 1024 * 10)  # 10 KB

        self.storage = AIStorageManager(
            hf_hub_path=self.hf_dir,
            torch_path=self.torch_dir,
            claude_projects_path=self.claude_projects
        )

    def tearDown(self):
        self.temp_dir.cleanup()

    def test_scan_storage(self):
        data = self.storage.scan_all()
        self.assertIn("models", data)
        self.assertIn("workspaces", data)

        hf_models = [m for m in data["models"] if m["source"] == "huggingface"]
        self.assertEqual(len(hf_models), 1)
        self.assertEqual(hf_models[0]["name"], "bert-base-uncased")
        self.assertGreaterEqual(hf_models[0]["size_bytes"], 50 * 1024)

        torch_models = [m for m in data["models"] if m["source"] == "torch"]
        self.assertEqual(len(torch_models), 1)
        self.assertEqual(torch_models[0]["name"], "resnet50.pth")

        workspaces = data["workspaces"]
        self.assertGreater(len(workspaces), 0)

    def test_delete_model(self):
        models = self.storage.scan_all()["models"]
        hf_model = next(m for m in models if m["source"] == "huggingface")
        res = self.storage.delete_model(hf_model["id"])
        self.assertTrue(res["success"])
        self.assertFalse((self.hf_dir / "models--bert-base-uncased").exists())


class TestAIApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
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

    def test_ai_skills_api(self):
        import urllib.request
        import json
        url = f"http://127.0.0.1:{self.port}/api/ai/skills"
        req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("skills", data)
            self.assertIn("categories", data)
            self.assertIn("targets", data)

    def test_ai_storage_api(self):
        import urllib.request
        import json
        url = f"http://127.0.0.1:{self.port}/api/ai/storage"
        req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("models", data)
            self.assertIn("workspaces", data)

    def test_ai_status_api(self):
        import urllib.request
        import json
        url = f"http://127.0.0.1:{self.port}/api/ai/status"
        req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1"})
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("services", data)


if __name__ == "__main__":
    unittest.main()
