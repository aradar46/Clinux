import tempfile
import unittest
from pathlib import Path

from clinux.runner import Runner, CommandNotFoundError, ClinuxPermissionError, ExecutionError
from clinux.capabilities import CapabilityRegistry
from clinux.config import Config
from clinux.modules import registry
from clinux.modules.base import BaseModule


class TestCoreArchitecture(unittest.TestCase):
    def test_runner_dry_run_and_execution(self):
        r = Runner(dry_run=True)
        res = r.run(["echo", "hello"])
        self.assertTrue(res.dry_run)
        self.assertEqual(res.returncode, 0)
        self.assertIn("[DRY-RUN] Would execute:", res.stdout)

        r_real = Runner(dry_run=False)
        res_real = r_real.run(["echo", "hello"])
        self.assertFalse(res_real.dry_run)
        self.assertEqual(res_real.returncode, 0)
        self.assertIn("hello", res_real.stdout)

    def test_runner_missing_command(self):
        r = Runner(dry_run=False)
        with self.assertRaises(CommandNotFoundError):
            r.run(["non_existent_binary_xyz_123"])

    def test_capabilities_detection(self):
        caps = CapabilityRegistry()
        self.assertTrue(caps.has("runtime.python"))

    def test_config_manager(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            cfg_file = Path(tmpdir) / "config.json"
            cfg = Config(config_path=cfg_file)
            self.assertEqual(cfg.get("general.default_port"), 8421)

            cfg.set("general.default_port", 9000)
            self.assertEqual(cfg.get("general.default_port"), 9000)

            # Reload
            cfg_reloaded = Config(config_path=cfg_file)
            self.assertEqual(cfg_reloaded.get("general.default_port"), 9000)

    def test_module_registry(self):
        mods = registry.list_all()
        mod_ids = [m.id for m in mods]
        self.assertIn("cleaner", mod_ids)
        self.assertIn("apps", mod_ids)
        self.assertIn("security", mod_ids)

        cleaner = registry.get("cleaner")
        self.assertIsNotNone(cleaner)
        scan = cleaner.scan()
        self.assertIn("targets", scan)


if __name__ == "__main__":
    unittest.main()
