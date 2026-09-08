import os
import pty
import select
import signal
import struct
import fcntl
import termios
import time
import uuid
import threading
from pathlib import Path
from typing import Dict, Optional, Any


class TerminalSession:
    """Manages an individual pseudo-terminal (PTY) session running a shell."""

    def __init__(self, cols: int = 80, rows: int = 24, cwd: Optional[str] = None):
        self.id = str(uuid.uuid4())[:8]
        self.cols = max(10, min(cols, 500))
        self.rows = max(5, min(rows, 200))
        self.cwd = cwd or str(Path.home())
        self.created_at = time.time()
        self.last_activity = time.time()
        self.closed = False
        self._lock = threading.Lock()

        # Open pseudo-terminal master and slave
        self.master_fd, self.slave_fd = pty.openpty()
        self._set_winsize(self.cols, self.rows)

        env = os.environ.copy()
        env["TERM"] = "xterm-256color"
        env["COLORTERM"] = "truecolor"
        env["LANG"] = env.get("LANG", "en_US.UTF-8")

        shell = env.get("SHELL") or "/bin/bash"

        self.pid = os.fork()
        if self.pid == 0:
            # Child process: configure standard file descriptors to slave PTY
            os.close(self.master_fd)
            os.setsid()
            try:
                fcntl.ioctl(self.slave_fd, termios.TIOCSCTTY, 0)
            except Exception:
                pass

            os.dup2(self.slave_fd, 0)
            os.dup2(self.slave_fd, 1)
            os.dup2(self.slave_fd, 2)
            if self.slave_fd > 2:
                os.close(self.slave_fd)

            try:
                os.chdir(self.cwd)
            except Exception:
                os.chdir(str(Path.home()))

            try:
                os.execvpe(shell, [shell, "-l"], env)
            except Exception:
                os.execvpe("/bin/sh", ["/bin/sh"], env)
            os._exit(1)

        # Parent process: close slave descriptor
        os.close(self.slave_fd)

    def _set_winsize(self, cols: int, rows: int):
        winsize = struct.pack("HHHH", rows, cols, 0, 0)
        try:
            fcntl.ioctl(self.master_fd, termios.TIOCSWINSZ, winsize)
        except Exception:
            pass

    def resize(self, cols: int, rows: int):
        with self._lock:
            if self.closed:
                return
            self.cols = max(10, min(cols, 500))
            self.rows = max(5, min(rows, 200))
            self._set_winsize(self.cols, self.rows)
            self.last_activity = time.time()

    def write(self, data: bytes):
        with self._lock:
            if self.closed:
                return
            try:
                os.write(self.master_fd, data)
                self.last_activity = time.time()
            except OSError:
                self.close()

    def read(self, max_bytes: int = 4096, timeout: float = 0.05) -> bytes:
        if self.closed:
            return b""

        try:
            r, _, _ = select.select([self.master_fd], [], [], timeout)
            if self.master_fd in r:
                data = os.read(self.master_fd, max_bytes)
                if not data:
                    self.close()
                    return b""
                self.last_activity = time.time()
                return data
        except (OSError, ValueError):
            self.close()
            return b""
        return b""

    def is_alive(self) -> bool:
        if self.closed:
            return False
        try:
            pid, status = os.waitpid(self.pid, os.WNOHANG)
            if pid == self.pid:
                self.closed = True
                return False
            return True
        except ChildProcessError:
            self.closed = True
            return False

    def close(self):
        with self._lock:
            if not self.closed:
                self.closed = True
                try:
                    os.close(self.master_fd)
                except Exception:
                    pass
                try:
                    os.kill(self.pid, signal.SIGTERM)
                except Exception:
                    pass
                try:
                    os.waitpid(self.pid, os.WNOHANG)
                except Exception:
                    pass


class TerminalManager:
    """Manages active terminal sessions."""

    def __init__(self):
        self.sessions: Dict[str, TerminalSession] = {}
        self._lock = threading.Lock()

    def create_session(
        self,
        cols: int = 80,
        rows: int = 24,
        cwd: Optional[str] = None
    ) -> TerminalSession:
        self.cleanup_inactive()
        session = TerminalSession(cols=cols, rows=rows, cwd=cwd)
        with self._lock:
            self.sessions[session.id] = session
        return session

    def get_session(self, session_id: str) -> Optional[TerminalSession]:
        with self._lock:
            session = self.sessions.get(session_id)
            if session and not session.is_alive():
                session.close()
                del self.sessions[session_id]
                return None
            return session

    def close_session(self, session_id: str) -> bool:
        with self._lock:
            session = self.sessions.pop(session_id, None)
            if session:
                session.close()
                return True
            return False

    def cleanup_inactive(self, max_idle_seconds: float = 7200):
        now = time.time()
        with self._lock:
            to_remove = []
            for sid, s in self.sessions.items():
                if not s.is_alive() or (now - s.last_activity > max_idle_seconds):
                    s.close()
                    to_remove.append(sid)
            for sid in to_remove:
                self.sessions.pop(sid, None)

    def close_all(self):
        with self._lock:
            for s in self.sessions.values():
                s.close()
            self.sessions.clear()
