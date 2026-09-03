#!/usr/bin/env python3
"""
Clinux - Linux Cleaner & Portable App Manager
Thin entry point delegating to clinux.cli module.
"""

import sys
from pathlib import Path

# Ensure repo root is on sys.path
sys.path.insert(0, str(Path(__file__).parent.resolve()))

from clinux.cli import run_cli


def main():
    sys.exit(run_cli())


if __name__ == "__main__":
    main()
