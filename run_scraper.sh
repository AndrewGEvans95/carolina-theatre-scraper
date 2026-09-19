#!/bin/bash

# Set working directory
cd /opt/carolina-theatre-scraper

# Activate virtual environment
source venv/bin/activate

# Set up logging
# Single appended log so logrotate can rotate and expire it
LOG_FILE="/var/log/carolina-scraper/scraper.log"
exec > >(tee -a "$LOG_FILE")
exec 2>&1

echo "$(date): Starting Carolina Theatre scraper..."

# Set Chrome options for headless server environment
export DISPLAY=:99
export CHROME_BIN=/usr/bin/google-chrome-stable
export CHROME_PATH=/usr/bin/google-chrome-stable

# Run the scraper
python3 movie_scraper.py

# Check if scraper was successful
if [ $? -eq 0 ]; then
    echo "$(date): Scraper completed successfully"

    # Generate the website
    # No backup copies: they accumulate in the public web root, and the
    # page can be regenerated from the database at any time
    python3 site_generator.py -o /var/www/html/index.html --no-backup

    if [ $? -eq 0 ]; then
        echo "$(date): Website generated successfully"

        # Set proper permissions for web server
        chmod 644 /var/www/html/index.html
        chmod 644 /var/www/html/styles.css 2>/dev/null || true
        chmod 644 /var/www/html/daily-cinema.html 2>/dev/null || true
        chmod 644 /var/www/html/about.html 2>/dev/null || true
        chmod 644 /var/www/html/truth.html 2>/dev/null || true
        chmod 644 /var/www/html/drawing.png 2>/dev/null || true

        # Generate JSON (optional)
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

    else
        echo "$(date): ERROR: Website generation failed"
        exit 1
    fi
else
    echo "$(date): ERROR: Scraper failed"
    exit 1
fi

echo "$(date): All tasks completed successfully"
