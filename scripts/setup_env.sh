#!/bin/bash
# Setup script for Linux/macOS

# Work from the repository root, wherever this script is run from
cd "$(dirname "$0")/.." || exit 1

echo "Creating virtual environment..."
python3 -m venv venv

echo "Activating virtual environment..."
source venv/bin/activate

echo "Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

echo ""
echo "Setup complete! To activate the virtual environment, run:"
echo "  source venv/bin/activate"
echo ""
echo "Then run the application with:"
echo "  python reddit.py"
echo ""

