<div align="center">
  <img src="icon.png" alt="Clinux" width="120" height="120">
  <h1>Clinux</h1>
  <p>Linux cleaner, portable app manager, AI skill switcher, and dotfiles dashboard.<br>Python stdlib only, zero dependencies.</p>
</div>

## Features

- **Cleaner**: Purges package manager caches (Pacman, Yay, Flatpak, APT, DNF), Conda archives, dev caches (Pip, uv, Npm, Cargo, R), and system logs/trash. Shows exact sudo commands when root is needed.
- **App Manager**: Installs `.tar.gz`, `.tar.xz`, and `.zip` binaries into `~/.local/opt/` with desktop menu entries and `$PATH` symlinks.
- **AI & Skills**: Toggles agent skills on/off across Claude Code, Antigravity, and Codex. Prunes Hugging Face, PyTorch, and Ollama model weights and session logs.
- **Dotfiles**: Runs GNU Stow against `~/.dotfiles`, supports selective stow/unstow per package, and syncs GNOME settings (works just for me).

## Quick Start

Python 3.8+ only.

```bash
curl -fsSL https://raw.githubusercontent.com/aradar46/Clinux/main/install.sh | bash
```

Or run manually:

```bash
git clone https://github.com/aradar46/Clinux.git
cd Clinux
python3 app.py
```

##  Paths

| Item            | Path                                          |
| --------------- | --------------------------------------------- |
| Database        | `~/.local/share/clinux/apps.db`             |
| Apps            | `~/.local/opt/<app>/`                       |
| Binaries        | `~/.local/bin/<app>`                        |
| Desktop Entries | `~/.local/share/applications/<app>.desktop` |
| Dotfiles        | `~/.dotfiles/`                              |

## License

[GPL-3.0](LICENSE)
