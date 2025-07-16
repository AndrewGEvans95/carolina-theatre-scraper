#!/bin/bash

# Carolina Theatre Scraper - Ubuntu Server Deployment Script
# This script sets up the application on Ubuntu and configures automated updates

set -e  # Exit on any error

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Configuration
APP_DIR="/opt/carolina-theatre-scraper"
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

# Copy application files
echo -e "${YELLOW}Setting up application files...${NC}"
if [ -f "movie_scraper.py" ]; then
    cp -r . "$APP_DIR/"
    chown -R "$APP_USER:$APP_USER" "$APP_DIR"
else
    echo -e "${RED}Error: movie_scraper.py not found. Run this script from the project directory.${NC}"
    exit 1
fi

# Create Python virtual environment
echo -e "${YELLOW}Setting up Python virtual environment...${NC}"
sudo -u "$APP_USER" python3 -m venv "$APP_DIR/venv"
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install --upgrade pip
sudo -u "$APP_USER" "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"

# Create run script
echo -e "${YELLOW}Creating run script...${NC}"
cat > "$APP_DIR/run_scraper.sh" << 'EOF'
#!/bin/bash

# Set working directory
cd /opt/carolina-theatre-scraper

# Activate virtual environment
source venv/bin/activate

# Set up logging
LOG_FILE="/var/log/carolina-scraper/scraper-$(date +%Y%m%d-%H%M%S).log"
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
    python3 site_generator.py /var/www/html/index.html
    
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
        python3 json_generator.py > /var/www/html/showtimes.json 2>/dev/null || true
        chmod 644 /var/www/html/showtimes.json 2>/dev/null || true
        
    else
        echo "$(date): ERROR: Website generation failed"
        exit 1
    fi
else
    echo "$(date): ERROR: Scraper failed"
    exit 1
fi

echo "$(date): All tasks completed successfully"
EOF

chmod +x "$APP_DIR/run_scraper.sh"
chown "$APP_USER:$APP_USER" "$APP_DIR/run_scraper.sh"

# Note: nginx configuration skipped - using existing server configuration

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