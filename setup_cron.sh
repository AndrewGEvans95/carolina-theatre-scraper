#!/bin/bash

# Carolina Theatre Scraper - Cron Job Setup Script
# Sets up automated execution via cron

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

# Configuration
APP_USER="carolina-scraper"
CRON_SCHEDULE="0 */6 * * *"  # Every 6 hours
APP_DIR="/opt/carolina-theatre-scraper"

echo -e "${GREEN}Setting up cron job for Carolina Theatre Scraper...${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Check if app user exists
if ! id "$APP_USER" &>/dev/null; then
    echo -e "${RED}Application user '$APP_USER' not found. Run deploy.sh first.${NC}"
    exit 1
fi

# Create cron job for the application user
echo -e "${YELLOW}Creating cron job...${NC}"

# Create a temporary cron file in the app directory (where we have permissions)
TEMP_CRON="$APP_DIR/temp_cron_$$"

# Get existing cron jobs for the user (if any)
sudo -u "$APP_USER" crontab -l 2>/dev/null > "$TEMP_CRON" || touch "$TEMP_CRON"

# Set proper ownership for the temp file
chown "$APP_USER:$APP_USER" "$TEMP_CRON"

# Remove any existing carolina-theatre-scraper cron jobs
sed -i '/carolina-theatre-scraper/d' "$TEMP_CRON" 2>/dev/null || true

# Add new cron job
echo "$CRON_SCHEDULE $APP_DIR/run_scraper.sh # carolina-theatre-scraper" >> "$TEMP_CRON"

# Install the cron job
sudo -u "$APP_USER" crontab "$TEMP_CRON"

# Clean up
rm -f "$TEMP_CRON"

# Ensure cron service is running
systemctl enable cron
systemctl start cron

# Create a manual run script for testing
cat > "$APP_DIR/manual_run.sh" << 'EOF'
#!/bin/bash
echo "Running Carolina Theatre Scraper manually..."
sudo -u carolina-scraper /opt/carolina-theatre-scraper/run_scraper.sh
EOF

chmod +x "$APP_DIR/manual_run.sh"

echo -e "${GREEN}Cron job setup completed!${NC}"
echo -e "${YELLOW}Cron schedule: $CRON_SCHEDULE (every 6 hours)${NC}"
echo -e "${YELLOW}Manual run: sudo $APP_DIR/manual_run.sh${NC}"
echo -e "${YELLOW}View cron jobs: sudo -u $APP_USER crontab -l${NC}"
echo -e "${YELLOW}Monitor logs: tail -f /var/log/carolina-scraper/*.log${NC}"

# Show current cron jobs
echo -e "${YELLOW}Current cron jobs for $APP_USER:${NC}"
sudo -u "$APP_USER" crontab -l