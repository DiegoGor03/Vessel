# DistroBox Package Manager

A GNOME Software-like package manager that interfaces with distrobox containers.

# NOTE: AS IS STILL IN AN ALPHA STATE. USE WITH CAUTION

## Features

- 🐋 Manage Debian, Fedora, and Arch containers via distrobox
- 📦 Search and browse packages across all containers
- ⬇️ Install and remove packages from containers
- 🎨 Native GNOME UI built with GTK 4 and Libadwaita

## Requirements

- Python 3.10+
- GTK 4
- Libadwaita
- distrobox
- distrobox dependencies (podman or docker)

## Installation

**Automated (Recommended):**

```bash
chmod +x install.sh
./install.sh
```

The install script automatically:
- Detects your Linux distribution
- Installs system dependencies (GTK 4, Libadwaita, PyGObject, etc.)
- Installs distrobox if needed
- Creates a proper Python virtual environment with system site-packages access

**Manual Installation:**

If you prefer to install manually, ensure you have:

1. **System packages:**
   - **Fedora/RHEL/Nobara**: `sudo dnf install python3-gobject gtk4 libadwaita-devel gobject-introspection-devel cairo-devel pkg-config glib2-devel`
   - **Ubuntu/Debian**: `sudo apt-get install python3-gi gir1.2-gtk-4.0 gir1.2-adwaita-1 libcairo2-dev pkg-config libglib2.0-dev`
   - **Arch**: `sudo pacman -S python-gobject gtk4 libadwaita`

2. **Distrobox:**
   ```bash
   curl -s https://raw.githubusercontent.com/89luca89/distrobox/main/install | sudo bash
   ```

3. **Python venv:**
   ```bash
   python3 -m venv --system-site-packages .venv
   source .venv/bin/activate
   ```

## Usage

**Quick Start:**

```bash
./run.sh
```

Or run manually:

```bash
source .venv/bin/activate
python3 src/main.py
```

**First Run**: On first launch, the application automatically creates three distrobox containers:
- `distrobox-debian` (Debian Bookworm)
- `distrobox-fedora` (Fedora latest)
- `distrobox-arch` (Arch Linux latest)

This may take several minutes as container images are downloaded. Once complete, you can search for and install packages into any container.

**In VS Code:**

```
Ctrl+Shift+B -> Run DistroPackage Manager
```

## Project Structure

```
src/
├── main.py              # Application entry point
├── core/
│   ├── distrobox.py     # Container management
│   └── packages.py      # Package operations
└── ui/
    └── window.py        # GTK main window
```

## Architecture

- **Core Layer**: Manages distrobox containers and packages via subprocess calls
- **UI Layer**: GTK 4 + Libadwaita for GNOME-like interface
- **Threading**: Async operations prevent UI freezing during container operations

## License

MIT
