# Clinux

![Alt text](targz_manager/static/icon.png)

Self-hosted web UI and CLI for Linux system cleaning and portable app management. Zero dependencies.

## What it does

- **System Cleaner**: Purges package manager caches (Pacman, Yay, Paru, Flatpak, APT, DNF, Snap), Conda package archives (Miniforge, Miniconda, Micromamba), developer caches (Pip, uv, Poetry, Npm, Cargo, Go, Gradle, R), IDE caches, and system junk (thumbnails, Trash, coredumps).
- **Portable App Manager**: Installs `.tar.gz`, `.tar.xz`, and `.zip` binaries into `~/.local/opt/` with desktop menu shortcuts and `$PATH` symlinks. Upgrades and uninstalls cleanly.
- **AI Tooling & Skills Manager**: Discovers, activates, and deactivates agent skills across Claude Code, Antigravity, and Codex. Selectively inspects and prunes Hugging Face models, PyTorch checkpoints, Ollama models, and coding agent session caches.
- **Dotfiles Manager**: Direct dashboard and CLI wrapper for `~/.dotfiles/dotfiles` to preview, apply, and update GNU Stow links, sync GNOME settings, and export packages .
- **Sudo safety**: User-level caches clean in one click. Targets needing root privileges show the exact terminal command (`sudo pacman -Scc`, `sudo apt-get clean`) to copy and run yourself.

## Quick Start

Python 3.8+ only. No virtualenvs or `pip install` required.

```bash
curl -fsSL https://raw.githubusercontent.com/aradar46/targz-manager/main/install.sh | bash
```

Or run manually:

```bash
git clone https://github.com/aradar46/targz-manager.git
cd targz-manager
python3 app.py
```

## CLI

```bash
python3 app.py clean               # scan and clean caches
python3 app.py clean --dry-run     # preview reclaimable space
python3 app.py clean --all         # non-interactive clean
python3 app.py skills              # list and toggle agent skills
python3 app.py ai-storage          # inspect and prune AI models and agent caches
python3 app.py dotfiles            # check, apply, and sync ~/.dotfiles
python3 app.py install <file>      # install a portable tarball
python3 app.py list               # list managed apps
python3 app.py remove <app>        # uninstall an app
```

## Paths

| Item               | Path                                          |
| ------------------ | --------------------------------------------- |
| Database           | `~/.local/share/clinux/apps.db`             |
| Installed Apps     | `~/.local/opt/<app>/`                       |
| `$PATH` Symlinks | `~/.local/bin/<app>`                        |
| Desktop Entries    | `~/.local/share/applications/<app>.desktop` |

## License

[GPL-3.0](LICENSE)
