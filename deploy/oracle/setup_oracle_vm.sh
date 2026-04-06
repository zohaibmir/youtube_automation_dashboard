#!/usr/bin/env bash
set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/../.." && pwd)"

echo "Using repo: $REPO_DIR"

sudo apt-get update
sudo apt-get install -y \
  python3 \
  python3-venv \
  python3-pip \
  ffmpeg \
  git \
  curl

cd "$REPO_DIR"

if [[ ! -d .venv ]]; then
  python3 -m venv .venv
fi

source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt

mkdir -p data audio images output logs tokens

echo "Bootstrap complete."
echo "Next steps:"
echo "1. Copy .env, client_secrets.json, and tokens/ to this VM"
echo "2. Install systemd service templates from deploy/oracle/"
