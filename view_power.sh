#!/bin/bash

# Fetch the private power dashboard from the server and open it locally.
#
# The dashboard is deliberately not published: it is generated to
# /opt/carolina-theatre-scraper/private, which Apache does not serve. This
# copies that directory down and opens the page in a browser.
#
#   ./view_power.sh            open in a browser from a temporary copy
#   ./view_power.sh ~/somewhere  copy it there instead

set -euo pipefail

HOST="${DEPLOY_HOST:-carolinashowtimes}"
DEST="${1:-$(mktemp -d)/power-dashboard}"

mkdir -p "$DEST"

# Ask the server where the dashboard currently lives: an unlisted
# directory under the web root when published, otherwise the private one.
REMOTE_DIR=$(ssh "$HOST" 'T=/etc/carolina-scraper/power-path
if [ -r "$T" ]; then
    TOKEN=$(tr -d " \t\n\r" < "$T")
    [ -n "$TOKEN" ] && echo "/var/www/html/$TOKEN" && exit
fi
echo /opt/carolina-theatre-scraper/private')

case "$REMOTE_DIR" in
    /var/www/html/*)
        echo "Published at: https://carolinashowtimes.com/${REMOTE_DIR#/var/www/html/}/power.html"
        ;;
    *)
        echo "Not published; reading the private copy"
        ;;
esac

# One connection: the server rate-limits ssh
scp -q "$HOST:$REMOTE_DIR/*" "$DEST/"

PAGE="$DEST/power.html"
if [ ! -f "$PAGE" ]; then
    echo "No power.html on the server yet - run ./deploy.sh first" >&2
    exit 1
fi

echo "Fetched $(date -r "$PAGE" '+%Y-%m-%d %H:%M' 2>/dev/null || echo '') copy:"
ls -la "$DEST"
echo
echo "$PAGE"

# Open it if we can; otherwise the path above is enough to do it by hand
if command -v open >/dev/null 2>&1; then
    open "$PAGE"
elif command -v xdg-open >/dev/null 2>&1; then
    xdg-open "$PAGE"
fi
