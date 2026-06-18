#!/bin/bash
set -e

cd "$(dirname "$0")"

# Use Python 3.12 if available (avoid Python 3.14 compatibility issues)
PYTHON_BIN=$(command -v python3.12 || command -v python3)

# Check if uv is available, fallback to pip
UV_BIN=$(command -v uv || true)

# Create virtual environment if not exists
if [ ! -d ".venv" ]; then
    if [ -n "$UV_BIN" ]; then
        "$UV_BIN" venv --python "$PYTHON_BIN" .venv
    else
        "$PYTHON_BIN" -m venv .venv
    fi
fi

source .venv/bin/activate

# Install dependencies
if [ -n "$UV_BIN" ]; then
    "$UV_BIN" pip install -r requirements.txt
else
    pip install -r requirements.txt
fi

# Install Playwright browsers
playwright install chromium

# Create browser profile directory
mkdir -p browser_profile

# Default to Mac ClashX proxy if not already set (used for Gamma/CLOB API + browser)
export BROWSER_PROXY="${BROWSER_PROXY:-http://127.0.0.1:7890}"

# Load environment variables if .env exists
if [ -f .env ]; then
    export $(grep -v '^#' .env | xargs)
fi

# Run the bridge
python main.py
