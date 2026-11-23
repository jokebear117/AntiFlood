#!/bin/sh
set -eu
runner="$HOME/.venvs/antiflood/bin/python"
if [ ! -x "$runner" ]; then
    echo 'AntiFlood Python environment is missing. Follow docs/RUNNING.md once in your default WSL distribution.'
    exit 1
fi
exec "$runner" -m antiflood.launch
