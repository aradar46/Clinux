"""
Centralized directory and file path constants for Clinux.
"""

from pathlib import Path

HOME = Path.home()

# XDG Base Directories
XDG_CONFIG_HOME = Path(HOME) / ".config"
XDG_DATA_HOME = Path(HOME) / ".local" / "share"
XDG_CACHE_HOME = Path(HOME) / ".cache"

# Clinux Specific Paths
CLINUX_CONFIG_DIR = XDG_CONFIG_HOME / "clinux"
CLINUX_DATA_DIR = XDG_DATA_HOME / "clinux"
CLINUX_CACHE_DIR = XDG_CACHE_HOME / "clinux"

DEFAULT_DB_PATH = CLINUX_DATA_DIR / "apps.db"
DEFAULT_CONFIG_PATH = CLINUX_CONFIG_DIR / "config.json"

# Package / App Manager Paths
DEFAULT_OPT_DIR = HOME / ".local" / "opt"
DEFAULT_BIN_DIR = HOME / ".local" / "bin"
DEFAULT_DESKTOP_DIR = XDG_DATA_HOME / "applications"

# Dotfiles
DEFAULT_DOTFILES_DIR = HOME / ".dotfiles"
