#!/usr/bin/env bash
# Clinux - Linux Cleaner & Portable App Manager
#   curl -fsSL https://raw.githubusercontent.com/aradar46/Clinux/main/install.sh | bash
set -e

REPO_URL="https://github.com/aradar46/Clinux.git"
TARBALL_URL="https://github.com/aradar46/Clinux/archive/refs/heads/main.tar.gz"
INSTALL_DIR="$HOME/.local/opt/clinux"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Error: python3 is required but was not found on PATH." >&2
  exit 1
fi

mkdir -p "$(dirname "$INSTALL_DIR")"

if [ -d "$INSTALL_DIR/.git" ]; then
  echo "Updating existing install at $INSTALL_DIR..."
  git -C "$INSTALL_DIR" reset --hard HEAD
  git -C "$INSTALL_DIR" pull --ff-only
elif command -v git >/dev/null 2>&1; then
  echo "Cloning Clinux into $INSTALL_DIR..."
  rm -rf "$INSTALL_DIR"
  git clone --depth 1 "$REPO_URL" "$INSTALL_DIR"
else
  echo "Downloading Clinux into $INSTALL_DIR..."
  rm -rf "$INSTALL_DIR"
  mkdir -p "$INSTALL_DIR"
  curl -fsSL "$TARBALL_URL" | tar -xz -C "$INSTALL_DIR" --strip-components=1
fi

echo "Adding desktop launcher entry..."
python3 "$INSTALL_DIR/app.py" --install-desktop-entry

echo "Starting Clinux..."
python3 "$INSTALL_DIR/app.py"
