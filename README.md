<img src="targz_manager/static/icon.svg" width="30" align="left" alt="TarGz Manager icon">

# TarGz Manager

**A zero-dependency web UI for installing, updating, and cleanly removing `.tar.gz` / `.tar.xz` portable Linux applications.**

Linux distributes a lot of software as plain tarballs with no package manager behind them: no `$PATH` entry, no application menu shortcut, no upgrade path, no clean uninstall. TarGz Manager is a small self-hosted tool that fixes that, extract an archive once, and it handles the desktop integration, symlinks, versioning, and removal for you.

![TarGz Manager screenshot](screenshot.png)

## Why

Downloading a pre-built Linux binary as a `.tar.gz` usually leaves you with a folder that has none of the conveniences a proper package gives you:

- No entry in your application launcher (GNOME/KDE/XFCE)
- No command available from the terminal
- No record of what version you have or where you put it
- No clean way to remove it without hunting down loose files

TarGz Manager tracks all of that in a local SQLite database and automates the boring parts.

## Features

- Install `.tar.gz`, `.tgz`, `.tar.xz`, `.tar.bz2`, and `.zip` archives into a clean, isolated directory (`~/.local/opt/<app>/`)
- Auto-detects the main executable and icon inside an archive, with confidence scoring
- Flattens single wrapper folders on extraction (e.g. `blender-4.1.0-linux-x64/`)
- Generates a `.desktop` launcher entry and a `~/.local/bin` symlink
- In-place upgrades with automatic rollback if extraction fails
- One-click clean uninstall (files, shortcut, symlink, and database entry)
- Scans `/opt`, `~/.local/opt`, `~/Applications`, and existing `.desktop` files for apps you already installed by hand, so you can bring them under management
- Clean Master cache cleaner: scan and purge package manager caches (Pacman, Yay, Paru, Flatpak, APT, DNF, Snap), Conda package tarballs (Miniforge, Miniconda, Micromamba), developer runtimes (Pip, uv, Poetry, Npm, Yarn, Pnpm, Go, Cargo, Gradle, R), IDEs (VS Code, VSCodium, JetBrains), and desktop junk (thumbnails, trash, core dumps)
- Safe elevation workflow: user-level caches clean with one click, while root targets show the exact copyable terminal command (e.g. `sudo pacman -Scc`, `sudo apt-get clean`) without capturing passwords
- Full CLI for scripting, alongside the web UI

## Clean Master

TarGz Manager includes a built-in cleaner to identify and reclaim gigabytes of disk space consumed by build tools, package managers, and runtime caches:

- **Package Managers**: Pacman, Yay, Paru, Flatpak, APT (Debian/Ubuntu), DNF (Fedora/RHEL), Snap cache.
- **Conda and Python Ecosystem**: Miniforge, Miniconda, Conda, and Micromamba package tarballs (`.conda` and `.tar.bz2` archives are safely pruned without affecting active environments), uv, Poetry, and Pip caches.
- **Developer Tools**: Npm, Yarn, Pnpm, Cargo (crates and git db), Go build cache, Gradle caches, R package cache.
- **IDEs and Editors**: VS Code, VSCodium, and JetBrains IDE caches.
- **Containers and Workflows**: Podman storage temp, Nextflow, and Snakemake caches.
- **System Junk**: Desktop thumbnails, desktop Trash, systemd crash core dumps, and Debian/Ubuntu crash reports.

For targets requiring root permissions, TarGz Manager never asks for or stores your sudo password. Instead, it displays the exact terminal command to run directly in your shell (e.g. `sudo pacman -Scc`), with a one-click copy button and a refresh action.

## Install

Requires Python 3.8+ and nothing else, no `pip install`, no virtualenv.

```bash
curl -fsSL https://raw.githubusercontent.com/aradar46/targz-manager/main/install.sh | bash
```

This clones the repo into `~/.local/opt/targz-manager`, adds it to your application menu, starts the server, and opens `http://127.0.0.1:8421/` in your browser. Run the same command again later to update.

Prefer to do it by hand?

```bash
git clone https://github.com/aradar46/targz-manager.git
cd targz-manager
python3 app.py                    # start the server + open the browser
python3 app.py --install-desktop-entry  # optional: add an app menu entry
```

## CLI

```bash
python3 app.py import-discovered  # find and import unmanaged apps/tarballs on your system
python3 app.py list               # list managed apps
python3 app.py inspect <archive>  # preview an archive without installing it
python3 app.py install <archive>  # install a tarball
python3 app.py update <app> <archive>  # upgrade an app in place
python3 app.py remove <app>        # uninstall cleanly
python3 app.py clean               # scan and clean package manager caches and junk files
python3 app.py clean --dry-run     # preview reclaimable space without deleting anything
python3 app.py clean --all         # clean all safe targets non-interactively
python3 app.py clean --targets yay pip miniforge_pkgs  # clean specific targets
python3 app.py launch <app>        # launch an app
python3 app.py --install-desktop-entry  # add TarGz Manager itself to your app menu
```

## Where things live

| Resource           | Path                                          |
| ------------------ | --------------------------------------------- |
| Database           | `~/.local/share/targz-manager/apps.db`      |
| Installed apps     | `~/.local/opt/<app>/`                       |
| `$PATH` symlinks   | `~/.local/bin/<app>`                        |
| Desktop entries    | `~/.local/share/applications/<app>.desktop` |

## Testing

```bash
python3 -m unittest discover -s tests -p "test_*.py" -v
```

## License

[GPL-3.0](LICENSE), this is a personal project, built to scratch my own itch. Issues and PRs are welcome but expect it to move at a hobby pace.
