import json
import time
import shutil
import tempfile
import unittest
import urllib.request
import threading
from pathlib import Path

from core.terminal_manager import TerminalSession, TerminalManager
from core.db import Database
from core.installer import Installer
from core.server import create_server


class TestTerminalSession(unittest.TestCase):
    def test_session_lifecycle(self):
        session = TerminalSession(cols=80, rows=24)
        try:
            self.assertTrue(session.is_alive())
            self.assertEqual(session.cols, 80)
            self.assertEqual(session.rows, 24)

            # Resize
            session.resize(100, 30)
            self.assertEqual(session.cols, 100)
            self.assertEqual(session.rows, 30)

            # Write and read
            session.write(b"echo CLINUX_TEST_OUTPUT\n")
            received = b""
            start = time.time()
            while time.time() - start < 3.0:
                chunk = session.read(timeout=0.1)
                if chunk:
                    received += chunk
                    if b"CLINUX_TEST_OUTPUT" in received:
                        break

            self.assertIn(b"CLINUX_TEST_OUTPUT", received)
        finally:
            session.close()
            self.assertFalse(session.is_alive())

    def test_manager_lifecycle(self):
        mgr = TerminalManager()
        s1 = mgr.create_session(cols=90, rows=25)
        sid = s1.id
        self.assertIn(sid, mgr.sessions)
        self.assertEqual(mgr.get_session(sid), s1)

        mgr.close_session(sid)
        self.assertIsNone(mgr.get_session(sid))
        self.assertNotIn(sid, mgr.sessions)


class TestTerminalHttpApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp_dir = Path(tempfile.mkdtemp(prefix="clinux_term_api_test_"))
        cls.db_path = cls.temp_dir / "term_api.db"
        cls.db = Database(cls.db_path)
        cls.installer = Installer(cls.db)

        cls.port = 8545
        cls.server = create_server(host="127.0.0.1", port=cls.port, installer=cls.installer)

        cls.server_thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.server_thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        shutil.rmtree(cls.temp_dir, ignore_errors=True)

    def test_terminal_api_flow(self):
        # 1. Create session
        create_url = f"http://127.0.0.1:{self.port}/api/terminal/create"
        payload = json.dumps({"cols": 80, "rows": 24}).encode("utf-8")
        req = urllib.request.Request(create_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertIn("session_id", data)
            session_id = data["session_id"]

        # 2. Resize session
        resize_url = f"http://127.0.0.1:{self.port}/api/terminal/resize"
        payload = json.dumps({"session_id": session_id, "cols": 120, "rows": 35}).encode("utf-8")
        req = urllib.request.Request(resize_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))
            self.assertEqual(data.get("cols"), 120)

        # 3. Send input
        input_url = f"http://127.0.0.1:{self.port}/api/terminal/input"
        payload = json.dumps({"session_id": session_id, "data": "echo HELLO_API\n"}).encode("utf-8")
        req = urllib.request.Request(input_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))

        # 4. Read stream (short read)
        stream_url = f"http://127.0.0.1:{self.port}/api/terminal/stream?session_id={session_id}"
        req = urllib.request.Request(stream_url)
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            # Read first chunk
            chunk = resp.read(256)
            self.assertTrue(len(chunk) > 0)

        # 5. Close session
        close_url = f"http://127.0.0.1:{self.port}/api/terminal/close"
        payload = json.dumps({"session_id": session_id}).encode("utf-8")
        req = urllib.request.Request(close_url, data=payload, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertTrue(data.get("success"))


if __name__ == "__main__":
    unittest.main()
