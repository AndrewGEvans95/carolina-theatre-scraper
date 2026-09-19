#!/bin/bash

# Rebuild the published pages from the database already on disk, without
# scraping anything. Used by `./deploy.sh --no-scrape` when only the
# generators or templates changed: a full run re-fetches 66 film pages for
# data that hasn't moved, which is slow and pointless.

# Set working directory
cd /opt/carolina-theatre-scraper

# Activate virtual environment
source venv/bin/activate

# Same log as the scheduled runs
LOG_FILE="/var/log/carolina-scraper/scraper.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo "$(date): Rebuilding pages from the stored database (no scrape)..."

python3 site_generator.py -o /var/www/html/index.html --no-backup

if [ $? -eq 0 ]; then
    chmod 644 /var/www/html/index.html
    chmod 644 /var/www/html/styles.css 2>/dev/null || true
    chmod 644 /var/www/html/daily-cinema.html 2>/dev/null || true
    chmod 644 /var/www/html/about.html 2>/dev/null || true
    chmod 644 /var/www/html/truth.html 2>/dev/null || true
    chmod 644 /var/www/html/drawing.png 2>/dev/null || true

    python3 json_generator.py /var/www/html/showtimes.json || true
    chmod 644 /var/www/html/showtimes.json 2>/dev/null || true

    # Where the dashboard is published. With no token file it stays
    # private, in a directory Apache does not serve. Writing a token to
    # /etc/carolina-scraper/power-path publishes it at an unlisted URL;
    # deleting that file takes it private again on the next run.
    POWER_DIR="/opt/carolina-theatre-scraper/private"
    POWER_TOKEN_FILE="/etc/carolina-scraper/power-path"
    if [ -r "$POWER_TOKEN_FILE" ]; then
        POWER_TOKEN=$(tr -d " \t\n\r" < "$POWER_TOKEN_FILE")
        [ -n "$POWER_TOKEN" ] && POWER_DIR="/var/www/html/$POWER_TOKEN"
    fi
    mkdir -p "$POWER_DIR"
    python3 power_generator.py -o "$POWER_DIR" || true

    echo "$(date): Pages rebuilt successfully"
else
    echo "$(date): ERROR: Website generation failed"
    exit 1
fi
