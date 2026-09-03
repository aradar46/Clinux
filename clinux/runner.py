"""
Centralized subprocess runner for Clinux.
Handles execution, dry-run simulation, timeouts, env vars, and root/sudo requirement detection.
"""

import os
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Union, Dict, Any
from clinux.errors import CommandNotFoundError, ExecutionError, ClinuxPermissionError


@dataclass
class CommandResult:
    command: List[str]
    returncode: int
    stdout: str
    stderr: str
    dry_run: bool = False

    @property
    def success(self) -> bool:
        return self.returncode == 0


class Runner:
    def __init__(self, dry_run: bool = False, verbose: bool = False):
        self.dry_run = dry_run
        self.verbose = verbose

    def run(
        self,
        cmd: Union[List[str], str],
        requires_root: bool = False,
        dry_run: Optional[bool] = None,
        timeout: Optional[float] = None,
        cwd: Optional[str] = None,
        env: Optional[Dict[str, str]] = None,
        check: bool = False,
    ) -> CommandResult:
        is_dry_run = self.dry_run if dry_run is None else dry_run

        if isinstance(cmd, str):
            command_list = [cmd]
        else:
            command_list = list(cmd)

        if not command_list:
            raise ValueError("Command list cannot be empty.")

        binary = command_list[0]
        if not shutil.which(binary) and not os.path.isabs(binary):
            if is_dry_run:
                pass
            else:
                raise CommandNotFoundError(f"Command '{binary}' not found on PATH.")

        if requires_root and os.geteuid() != 0:
            if not is_dry_run and not shutil.which("sudo") and not shutil.which("pkexec"):
                raise ClinuxPermissionError(f"Root privilege required for '{binary}' but sudo/pkexec not found.")

        if is_dry_run:
            simulated_cmd = (["sudo"] + command_list) if (requires_root and os.geteuid() != 0) else command_list
            return CommandResult(
                command=simulated_cmd,
                returncode=0,
                stdout=f"[DRY-RUN] Would execute: {' '.join(simulated_cmd)}",
                stderr="",
                dry_run=True,
            )

        exec_cmd = command_list
        if requires_root and os.geteuid() != 0:
            exec_cmd = ["sudo", "-n"] + command_list

        try:
            proc = subprocess.run(
                exec_cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                timeout=timeout,
                cwd=cwd,
                env=env,
            )
            res = CommandResult(
                command=exec_cmd,
                returncode=proc.returncode,
                stdout=proc.stdout,
                stderr=proc.stderr,
                dry_run=False,
            )
            if check and not res.success:
                raise ExecutionError(
                    f"Command '{' '.join(exec_cmd)}' failed with exit code {proc.returncode}: {proc.stderr}",
                    returncode=proc.returncode,
                    stdout=proc.stdout,
                    stderr=proc.stderr,
                )
            return res
        except subprocess.TimeoutExpired as e:
            raise ExecutionError(f"Command '{' '.join(exec_cmd)}' timed out after {timeout} seconds.") from e
        except Exception as e:
            if isinstance(e, ExecutionError):
                raise
            raise ExecutionError(f"Failed to execute '{' '.join(exec_cmd)}': {e}") from e


runner = Runner()
