#!/bin/bash

# Carolina Theatre Scraper - Deploy
# Run from your machine: pulls origin/main into the server checkout,
# installs requirements, and regenerates the site.
# Uses a single SSH connection (the server rate-limits SSH with ufw).

set -euo pipefail

HOST="${DEPLOY_HOST:-carolinashowtimes}"
BRANCH="main"

# --no-scrape rebuilds the pages from the database already on the server.
# Use it when only generators, templates or styles changed: a full run
# re-fetches 66 film pages for data that hasn't moved.
RUN_SCRIPT="manual_run.sh"
if [ "${1:-}" = "--no-scrape" ]; then
    RUN_SCRIPT="regenerate.sh"
    echo "Deploying without a scrape: pages will be rebuilt from the stored data"
fi

git fetch -q origin "$BRANCH"
if [ "$(git rev-parse HEAD)" != "$(git rev-parse "origin/$BRANCH")" ]; then
    echo "Note: local HEAD differs from origin/$BRANCH; deploying origin/$BRANCH ($(git rev-parse --short "origin/$BRANCH"))"
fi

ssh "$HOST" BRANCH="$BRANCH" RUN_SCRIPT="$RUN_SCRIPT" bash -s <<'EOF'
set -euo pipefail
APP_DIR=/opt/carolina-theatre-scraper
APP_USER=carolina-scraper

cd "$APP_DIR"
echo "Before: $(sudo -u "$APP_USER" git log --oneline -1)"
sudo -u "$APP_USER" git pull --ff-only origin "$BRANCH"
echo "After:  $(sudo -u "$APP_USER" git log --oneline -1)"

# python -m pip, not venv/bin/pip: the venv was copied from another path, so
# the console scripts' shebangs point at an interpreter this user can't read
sudo -u "$APP_USER" venv/bin/python -m pip install -q -r requirements.txt

if [ "$RUN_SCRIPT" = "regenerate.sh" ]; then
    sudo -u "$APP_USER" "$APP_DIR/regenerate.sh"
else
    "$APP_DIR/manual_run.sh"
fi
EOF
