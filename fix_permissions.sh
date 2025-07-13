#!/bin/bash

# Fix permissions for existing deployment
# Run this script if you're getting permission errors

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}Fixing permissions for Carolina Theatre Scraper...${NC}"

# Check if running as root
if [[ $EUID -ne 0 ]]; then
   echo -e "${RED}This script must be run as root (use sudo)${NC}"
   exit 1
fi

APP_USER="carolina-scraper"
WEB_DIR="/var/www/html"

# Add application user to www-data group
echo -e "${YELLOW}Adding $APP_USER to www-data group...${NC}"
usermod -a -G www-data "$APP_USER"

# Fix web directory permissions
echo -e "${YELLOW}Setting web directory permissions...${NC}"
chown -R "$APP_USER:www-data" "$WEB_DIR"
chmod -R 775 "$WEB_DIR"

# Test permissions
echo -e "${YELLOW}Testing write permissions...${NC}"
sudo -u "$APP_USER" touch "$WEB_DIR/test_write.txt"
if [ $? -eq 0 ]; then
    sudo -u "$APP_USER" rm "$WEB_DIR/test_write.txt"
    echo -e "${GREEN}✓ Write permissions working correctly${NC}"
else
    echo -e "${RED}✗ Write permissions still not working${NC}"
    exit 1
fi

echo -e "${GREEN}Permissions fixed! You can now run the scraper.${NC}"