#!/bin/zsh
set -euo pipefail

APP_ROOT="${0:A:h}"
exec "$APP_ROOT/start-codex.command"
