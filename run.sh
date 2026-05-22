#!/bin/bash

# Launcher script for DistroBox Package Manager

cd "$(dirname "$0")"

# Activate virtual environment
if [ ! -d ".venv" ]; then
    echo "❌ Virtual environment not found. Please run './install.sh' first."
    exit 1
fi

source .venv/bin/activate

# Run the application
python3 src/main.py "$@"
