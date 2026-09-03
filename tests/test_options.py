import json
import tempfile
import shutil
import unittest
import urllib.request
from pathlib import Path

from targz_manager.db import Database, DEFAULT_OPTIONS
from targz_manager.installer import Installer
from targz_manager.server import create_server


class TestOptionsManager(unittest.TestCase):
    def setUp(self):
        self.temp_dir = Path(tempfile.mkdtemp(prefix="clinux_options_test_"))
        self.db_path = self.temp_dir / "options_test.db"
        self.db = Database(self.db_path)

    def tearDown(self):
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_database_default_options(self):
        opts = self.db.get_options()
        self.assertIn("tabs", opts)
        self.assertIn("appearance", opts)
        self.assertIn("behavior", opts)
        self.assertIn("modules", opts)
        self.assertEqual(len(opts["tabs"]), 9)
        self.assertEqual(opts["appearance"]["theme"], "classic-green")

    def test_database_save_and_merge_options(self):
        custom_opts = self.db.get_options()
        custom_opts["appearance"]["theme"] = "amber-crt"
        custom_opts["appearance"]["crt_effects"] = False
        custom_opts["tabs"][0]["visible"] = False

        saved = self.db.save_options(custom_opts)
        self.assertEqual(saved["appearance"]["theme"], "amber-crt")
        self.assertFalse(saved["appearance"]["crt_effects"])
        self.assertFalse(saved["tabs"][0]["visible"])

        fetched = self.db.get_options()
        self.assertEqual(fetched["appearance"]["theme"], "amber-crt")
        self.assertFalse(fetched["appearance"]["crt_effects"])
        self.assertFalse(fetched["tabs"][0]["visible"])

    def test_database_reset_options(self):
        custom_opts = self.db.get_options()
        custom_opts["appearance"]["theme"] = "midnight"
        self.db.save_options(custom_opts)

        res = self.db.reset_options()
        self.assertEqual(res["appearance"]["theme"], "classic-green")

        fetched = self.db.get_options()
        self.assertEqual(fetched["appearance"]["theme"], "classic-green")


class TestOptionsApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="clinux_api_options_test_"))
        cls.db_path = cls.temp_dir / "api_options.db"
        cls.db = Database(cls.db_path)
        cls.installer = Installer(cls.db)

        cls.port = 8522
        cls.server = create_server(host="127.0.0.1", port=cls.port, installer=cls.installer)

        import threading
        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_get_and_post_options_api(self):
        # GET /api/options
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/options") as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode('utf-8'))
            self.assertIn("options", data)
            opts = data["options"]
            self.assertEqual(opts["appearance"]["theme"], "classic-green")

        # POST /api/options
        opts["appearance"]["theme"] = "midnight"
        req = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/options",
            data=json.dumps({"options": opts}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            res_data = json.loads(resp.read().decode('utf-8'))
            self.assertTrue(res_data.get("success"))
            self.assertEqual(res_data["options"]["appearance"]["theme"], "midnight")

        # Verify POST persistence
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}/api/options") as resp:
            data = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(data["options"]["appearance"]["theme"], "midnight")

        # Reset via API
        req_reset = urllib.request.Request(
            f"http://127.0.0.1:{self.port}/api/options",
            data=json.dumps({"action": "reset"}).encode('utf-8'),
            headers={"Content-Type": "application/json"}
        )
        with urllib.request.urlopen(req_reset) as resp:
            res_reset = json.loads(resp.read().decode('utf-8'))
            self.assertEqual(res_reset["options"]["appearance"]["theme"], "classic-green")

    def test_auxiliary_view_apis(self):
        for endpoint in ["/api/security/scan", "/api/projects/list", "/api/network/status", "/api/doctor"]:
            with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{endpoint}") as resp:
                self.assertEqual(resp.status, 200)


if __name__ == "__main__":
    unittest.main()
