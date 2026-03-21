## Getting Started

### Prerequisites

Before running the application, ensure you have:

1. **Python 3.10+** installed
2. **GTK 4** and **Libadwaita** libraries
3. **distrobox** installed
4. A container engine (**podman** or **docker**)

### Quick Install

Run the automated installation script:

```bash
chmod +x install.sh
./install.sh
```

This will:
- Check for required dependencies
- Create a Python virtual environment
- Install Python dependencies
- Install distrobox if needed

### Manual Installation

If you prefer manual setup:

1. Install system packages:
   ```bash
   # Ubuntu/Debian
   sudo apt install python3 python3-pip libgtk-4-1 libadwaita-1 podman

   # Fedora
   sudo dnf install python3 python3-pip gtk4 libadwaita podman

   # Arch
   sudo pacman -S python python-pip gtk4 libadwaita podman
   ```

2. Install distrobox:
   ```bash
   curl -s https://raw.githubusercontent.com/89luca89/distrobox/main/install | sudo bash
   ```

3. Create virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

4. Install Python dependencies:
   ```bash
   pip install -r requirements.txt
   ```

### Running the Application

```bash
# Ensure virtual environment is activated
source .venv/bin/activate

# Run the application
python3 src/main.py
```

**First Run**: On first launch, the application will automatically create three distrobox containers:
- `distrobox-debian`
- `distrobox-fedora`
- `distrobox-arch`

This may take several minutes as container images are downloaded.

## Usage

### Main Window

The application has a split view:

- **Left Panel**: Shows all available containers
- **Right Panel**: Shows packages and search results

### Searching for Packages

1. Select a container from the left panel
2. Type a package name in the search box
3. Results from all containers will appear
4. Click on a package to view details

### Installing Packages

1. Search for a package
2. Select it from the list
3. Click **Install** button
4. The package will be installed in the selected container

### Removing Packages

1. Search for an installed package
2. Select it from the list
3. Click **Remove** button
4. The package will be uninstalled from the container

## Troubleshooting

### "distrobox not found"
Make sure distrobox is installed and in your PATH:
```bash
distrobox --version
```

### "Cannot import gi"
Install PyGObject system packages:
```bash
# Ubuntu/Debian
sudo apt install python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adwaita-1

# Fedora
sudo dnf install python3-gobject gobject-introspection gobject-introspection-devel gtk4

# Arch
sudo pacman -S python-gobject gtk4
```

### "Certificate error" during installation
For podman/distrobox on some systems, you may need to configure certificate verification. See [distrobox documentation](https://distrobox.it/).

### Containers not starting
Check if your container engine (podman/docker) is properly installed and running:
```bash
podman --version
podman ps
```

## Architecture Overview

```
┌─────────────────────────────────────────┐
│  GTK 4 + Libadwaita UI (GNOME-like)      │
├─────────────────────────────────────────┤
│  PackageManager  │  DistroboxManager     │
│  - Search        │  - Create             │
│  - Install       │  - List               │
│  - Remove        │  - Start/Stop         │
├─────────────────────────────────────────┤
│  Distrobox (subprocess layer)            │
├─────────────────────────────────────────┤
│  Container Engine (podman/docker)       │
├─────────────────────────────────────────┤
│  Debian • Fedora • Arch Containers      │
└─────────────────────────────────────────┘
```

## Project Structure

```
distropackage/
├── src/
│   ├── main.py                 # Application entry point
│   ├── core/
│   │   ├── __init__.py
│   │   ├── distrobox.py        # Distrobox container management
│   │   └── packages.py         # Package search and operations
│   └── ui/
│       ├── __init__.py
│       └── window.py           # Main GTK window
├── requirements.txt            # Python dependencies
├── pyproject.toml             # Project metadata
├── README.md                  # Project overview
├── QUICKSTART.md              # This file
├── install.sh                 # Installation script
└── .gitignore
```

## Next Steps

- Customize the container selection and package managers
- Add container status monitoring
- Implement package update checking
- Add configuration file support for custom containers
- Create .desktop file for GNOME integration
- Add unit tests

## Contributing

Contributions are welcome! Please feel free to submit pull requests or report issues.
