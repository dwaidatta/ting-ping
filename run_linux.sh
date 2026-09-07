#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

venv_path=".venv"
activate_script="$venv_path/bin/activate"

if [[ ! -f "$activate_script" ]]; then
    echo "Virtual environment not found at '$venv_path'. Create it with: python3 -m venv .venv" >&2
    exit 1
fi

source "$activate_script"
python run.py