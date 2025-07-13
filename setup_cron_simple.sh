#!/bin/bash

# Simple cron setup - alternative method
# Run this if setup_cron.sh fails

echo "Setting up cron job (simple method)..."

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo "This script must be run as root (use sudo)"
   exit 1
fi

APP_USER="carolina-scraper"
CRON_SCHEDULE="0 */6 * * *"
APP_DIR="/opt/carolina-theatre-scraper"

# Check if app user exists
if ! id "$APP_USER" &>/dev/null; then
    echo "Application user '$APP_USER' not found. Run deploy.sh first."
    exit 1
fi

# Direct cron job installation
echo "Installing cron job for $APP_USER..."

# Use a here-document to create the cron entry directly
sudo -u "$APP_USER" bash -c "
(crontab -l 2>/dev/null | grep -v 'carolina-theatre-scraper' || true; echo '$CRON_SCHEDULE $APP_DIR/run_scraper.sh # carolina-theatre-scraper') | crontab -
"

if [ $? -eq 0 ]; then
    echo "✓ Cron job installed successfully"
else
    echo "✗ Failed to install cron job"
    exit 1
fi

# Ensure cron service is running
systemctl enable cron
systemctl start cron

echo "✓ Cron setup completed!"
echo "Schedule: $CRON_SCHEDULE (every 6 hours)"
echo ""
echo "View cron jobs:"
echo "sudo -u $APP_USER crontab -l"