"""
TarGz Manager
Zero-dependency package and application manager for manually extracted tarballs.
"""

__version__ = "1.0.0"

from .db import Database
from .installer import Installer
from .server import create_server
from .cleaner import SystemCleaner
from .ai_manager import SkillManager, AIStorageManager, AIRuntimeDetector
from .dotfiles_manager import DotfilesManager
from .disk_analyzer import DiskAnalyzer
