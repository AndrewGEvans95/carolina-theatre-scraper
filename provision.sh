#!/bin/bash

# Carolina Theatre Scraper - Ubuntu Server Provisioning Script
# One-time setup of a fresh server. Run on the server as root.
# For routine code updates, run ./deploy.sh from your machine instead.

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/opt/carolina-theatre-scraper"
REPO_URL="https://github.com/AndrewGEvans95/carolina-theatre-scraper.git"
APP_USER="carolina-scraper"
LOG_DIR="/var/log/carolina-scraper"
WEB_DIR="/var/www/html"
CRON_SCHEDULE="0 */6 * * *"  # Run every 6 hours

echo -e "${GREEN}Starting Carolina Theatre Scraper deployment...${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}"
   exit 1
fi

# Update system packages
echo -e "${YELLOW}Updating system packages...${NC}"
apt-get update
apt-get upgrade -y

# Install system dependencies
echo -e "${YELLOW}Installing system dependencies...${NC}"
apt-get install -y \
    python3 \
    python3-pip \
    python3-venv \
    git \
    curl \
    wget \
    unzip \
    cron \
    logrotate

# Install Google Chrome and dependencies
echo -e "${YELLOW}Installing Google Chrome and dependencies...${NC}"
if ! command -v google-chrome &> /dev/null; then
    # Add Chrome repository
    wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add -
    echo "deb [arch=amd64] http://dl.google.com/linux/chrome/deb/ stable main" > /etc/apt/sources.list.d/google-chrome.list
    apt-get update
    
    # Install Chrome and required dependencies
    apt-get install -y \
        google-chrome-stable \
        fonts-liberation \
        libasound2 \
        libatk-bridge2.0-0 \
        libdrm2 \
        libgtk-3-0 \
        libgtk-4-1 \
        libu2f-udev \
        libvulkan1 \
        xdg-utils
fi

# Install additional dependencies for headless Chrome
echo -e "${YELLOW}Installing additional Chrome dependencies...${NC}"
apt-get install -y \
    libnss3 \
    libgconf-2-4 \
    libxss1 \
    libappindicator1 \
    fonts-liberation \
    libappindicator3-1 \
    libasound2 \
    libatk-bridge2.0-0 \
    libdrm2 \
    libxcomposite1 \
    libxdamage1 \
    libxrandr2 \
    libgbm1

# Create application user
echo -e "${YELLOW}Creating application user...${NC}"
if ! id "$APP_USER" &>/dev/null; then
    useradd -r -d "$APP_DIR" -s /bin/bash "$APP_USER"
fi

# Add application user to www-data group for web directory access
usermod -a -G www-data "$APP_USER"

# Create directories
echo -e "${YELLOW}Creating application directories...${NC}"
mkdir -p "$APP_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$WEB_DIR"

# Set ownership and permissions
chown -R "$APP_USER:$APP_USER" "$APP_DIR"
chown -R "$APP_USER:$APP_USER" "$LOG_DIR"
chown -R "$APP_USER:www-data" "$WEB_DIR"
chmod -R 775 "$WEB_DIR"

# Clone application code (deploy.sh updates it later with git pull)
echo -e "${YELLOW}Setting up application files...${NC}"
if [ ! -d "$APP_DIR/.git" ]; then
    sudo -u "$APP_USER" git clone "$REPO_URL" "$APP_DIR"
fi

# Create Python virtual environment
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# run_scraper.sh and manual_run.sh come from the repository

# Note: Apache configuration skipped - using existing server configuration

# Set up log rotation
echo -e "${YELLOW}Configuring log rotation...${NC}"
cat > /etc/logrotate.d/carolina-scraper << 'EOF'
/var/log/carolina-scraper/*.log {
    daily
    missingok
    rotate 30
    compress
    delaycompress
    notifempty
    copytruncate
}
EOF

# Test run
echo -e "${YELLOW}Running initial test...${NC}"
sudo -u "$APP_USER" "$APP_DIR/run_scraper.sh"

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Test run successful!${NC}"
else
    echo -e "${RED}Test run failed. Check logs in $LOG_DIR${NC}"
    exit 1
fi

echo -e "${GREEN}Deployment completed successfully!${NC}"
echo -e "${YELLOW}Next steps:${NC}"
echo "1. Run the cron setup: sudo bash setup_cron.sh"
echo "2. Check the website at: https://carolinashowtimes.com"
echo "3. Monitor logs at: $LOG_DIR"
echo "4. JSON API available at: https://carolinashowtimes.com/showtimes.json"