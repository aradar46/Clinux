"""
System capability detector for Clinux.
Queries system binaries, package managers, runtimes, containers, and services.
"""

import shutil
from typing import Dict, Set


class CapabilityRegistry:
    def __init__(self):
        self._capabilities: Set[str] = set()
        self.detect()

    def detect(self) -> None:
        self._capabilities.clear()

        # Package Managers
        if shutil.which("pacman"):
            self._capabilities.add("package_manager.pacman")
        if shutil.which("yay"):
            self._capabilities.add("package_manager.yay")
        if shutil.which("paru"):
            self._capabilities.add("package_manager.paru")
        if shutil.which("apt") or shutil.which("apt-get"):
            self._capabilities.add("package_manager.apt")
        if shutil.which("dnf"):
            self._capabilities.add("package_manager.dnf")
        if shutil.which("flatpak"):
            self._capabilities.add("package_manager.flatpak")
        if shutil.which("snap"):
            self._capabilities.add("package_manager.snap")

        # Runtimes & Dev tools
        if shutil.which("python3") or shutil.which("python"):
            self._capabilities.add("runtime.python")
        if shutil.which("node") or shutil.which("npm"):
            self._capabilities.add("runtime.node")
        if shutil.which("cargo") or shutil.which("rustc"):
            self._capabilities.add("runtime.rust")
        if shutil.which("go"):
            self._capabilities.add("runtime.go")
        if shutil.which("stow"):
            self._capabilities.add("tool.stow")

        # Containers & Services
        if shutil.which("docker"):
            self._capabilities.add("container.docker")
        if shutil.which("podman"):
            self._capabilities.add("container.podman")
        if shutil.which("systemctl"):
            self._capabilities.add("service.systemd")

        # AI Tools
        if shutil.which("ollama"):
            self._capabilities.add("ai.ollama")
        if shutil.which("claude"):
            self._capabilities.add("ai.claude")
        if shutil.which("codex"):
            self._capabilities.add("ai.codex")

    def has(self, capability: str) -> bool:
        return capability in self._capabilities

    def get_all(self) -> Set[str]:
        return set(self._capabilities)


capabilities = CapabilityRegistry()
