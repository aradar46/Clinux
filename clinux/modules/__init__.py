"""
Clinux modules package and registry initialization.
"""

from clinux.modules.base import BaseModule, registry
from clinux.modules.cleaner import CleanerModule
from clinux.modules.apps import AppsModule
from clinux.modules.skills import SkillsModule
from clinux.modules.dotfiles import DotfilesModule
from clinux.modules.security import SecurityModule
from clinux.modules.machine import MachineModule
from clinux.modules.storage import StorageModule

# Register default modules
registry.register(CleanerModule())
registry.register(AppsModule())
registry.register(SkillsModule())
registry.register(DotfilesModule())
registry.register(SecurityModule())
registry.register(MachineModule())
registry.register(StorageModule())

__all__ = [
    "BaseModule",
    "registry",
    "CleanerModule",
    "AppsModule",
    "SkillsModule",
    "DotfilesModule",
    "SecurityModule",
    "MachineModule",
    "StorageModule",
]
