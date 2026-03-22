#!/bin/bash

# Installation script for DistroBox Package Manager

set -e

echo "🚀 Installing DistroBox Package Manager..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is required but not installed."
    exit 1
fi

PYTHON_VERSION=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
echo "✓ Python $PYTHON_VERSION found"

# Detect distro and install system dependencies
echo "📦 Installing system dependencies..."

if [ -f /etc/os-release ]; then
    . /etc/os-release
    OS=$ID
else
    echo "⚠️  Cannot detect OS. Please install GTK 4, Libadwaita, and development files manually."
    OS="unknown"
fi

case "$OS" in
    fedora|rhel|centos|nobara)
        echo "Detected Fedora/RHEL-based distro. Installing dependencies..."
        sudo dnf install -y python3-gobject gtk4 libadwaita-devel gobject-introspection-devel cairo-devel pkg-config glib2-devel
        ;;
    ubuntu|debian)
        echo "Detected Debian/Ubuntu. Installing dependencies..."
        sudo apt-get update
        sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adwaita-1 libcairo2-dev pkg-config libglib2.0-dev
        ;;
    arch)
        echo "Detected Arch. Installing dependencies..."
        sudo pacman -S --noconfirm python-gobject gtk4 libadwaita
        ;;
    *)
        # Try ID_LIKE as fallback
        if [[ "$ID_LIKE" == *"fedora"* || "$ID_LIKE" == *"rhel"* ]]; then
            echo "Detected Fedora-based distro (via ID_LIKE). Installing dependencies..."
            sudo dnf install -y python3-gobject gtk4 libadwaita-devel gobject-introspection-devel cairo-devel pkg-config glib2-devel
        elif [[ "$ID_LIKE" == *"debian"* ]]; then
            echo "Detected Debian-based distro (via ID_LIKE). Installing dependencies..."
            sudo apt-get update
            sudo apt-get install -y python3-gi python3-gi-cairo gir1.2-gtk-4.0 gir1.2-adwaita-1 libcairo2-dev pkg-config libglib2.0-dev
        else
            echo "⚠️  Unknown distro. Please install these packages manually:"
            echo "    - python3-gobject or python3-gi"
            echo "    - pyobject-introspection"
            echo "    - gtk4 development files"
            echo "    - libadwaita-devel or libadwaita-1"
            echo "    - cairo development files"
        fi
        ;;
esac

# Check distrobox
if ! command -v distrobox &> /dev/null; then
    echo "⚠️  distrobox is not installed. Installing..."
    curl -s https://raw.githubusercontent.com/89luca89/distrobox/main/install | sudo bash
fi

echo "✓ distrobox is installed"

# Create virtual environment with system site-packages
if [ ! -d ".venv" ]; then
    echo "📦 Creating Python virtual environment..."
    /usr/bin/python3 -m venv --system-site-packages .venv
else
    # Check if venv was created without system-site-packages and fix it
    if grep -q "include-system-site-packages = false" .venv/pyvenv.cfg; then
        echo "⚠️  Fixing venv configuration to include system site-packages..."
        rm -rf .venv
        /usr/bin/python3 -m venv --system-site-packages .venv
    fi
fi

# Activate virtual environment
echo "📦 Activating virtual environment..."
source .venv/bin/activate

# Install Python dependencies (minimal - GTK/Adwaita come from system)
if [ -s requirements.txt ]; then
    echo "📥 Installing Python dependencies..."
    pip install --upgrade pip
    pip install -r requirements.txt
else
    echo "✓ No additional Python dependencies needed"
fi

echo ""
echo "✅ Installation complete!"
echo ""
echo "To run the application:"
echo "  python3 src/main.py"
echo ""
echo "Or in VS Code:"
echo "  Ctrl+Shift+B -> Run DistroPackage Manager"
