import unittest
import json
from targz_manager.server import create_server
import urllib.request

class TestSecurityServerEndpoints(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = create_server(host="127.0.0.1", port=8912)
        import threading
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()

    def test_security_scan_api(self):
        url = "http://127.0.0.1:8912/api/security/scan"
        req = urllib.request.Request(url, headers={"Origin": "http://127.0.0.1:8912"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertIn("findings", data)
            self.assertIn("summary", data)

    def test_security_export_api(self):
        url = "http://127.0.0.1:8912/api/security/export"
        body = json.dumps({"format": "json"}).encode("utf-8")
        req = urllib.request.Request(url, data=body, headers={"Origin": "http://127.0.0.1:8912", "Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("content", data)


if __name__ == "__main__":
    unittest.main()
