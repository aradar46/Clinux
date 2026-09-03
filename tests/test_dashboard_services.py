import unittest
import tempfile
import json
import os
from pathlib import Path
from targz_manager.disk_analyzer import DiskAnalyzer
from targz_manager.server import create_server
import urllib.request

class TestDashboardAndServices(unittest.TestCase):
    def test_disk_analyzer_metrics(self):
        analyzer = DiskAnalyzer()
        res = analyzer.analyze()
        self.assertIn("total_bytes", res)
        self.assertIn("used_bytes", res)
        self.assertIn("free_bytes", res)
        self.assertIn("usage_percent", res)
        self.assertIn("health_percent", res)
        self.assertIn("health_status", res)
        self.assertIn("health_display_str", res)
        self.assertTrue(isinstance(res["health_percent"], int))

    def test_services_api_endpoint(self):
        server = create_server(host="127.0.0.1", port=0)
        port = server.server_port
        import threading
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/services", headers={"Origin": "http://127.0.0.1"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("services", data)
                self.assertTrue(isinstance(data["services"], list))
        finally:
            server.shutdown()

    def test_services_control_endpoint(self):
        server = create_server(host="127.0.0.1", port=0)
        port = server.server_port
        import threading
        t = threading.Thread(target=server.serve_forever, daemon=True)
        t.start()

        try:
            payload = json.dumps({"service": "nonexistent-test-service.service", "action": "restart"}).encode("utf-8")
            req = urllib.request.Request(f"http://127.0.0.1:{port}/api/services/control", data=payload, headers={"Content-Type": "application/json", "Origin": "http://127.0.0.1"}, method="POST")
            with urllib.request.urlopen(req, timeout=5) as resp:
                self.assertEqual(resp.status, 200)
                data = json.loads(resp.read().decode("utf-8"))
                self.assertIn("success", data)
        finally:
            server.shutdown()

if __name__ == "__main__":
    unittest.main()
