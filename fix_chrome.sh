#!/bin/bash

# Chrome Fix Script for Ubuntu Server
# Run this if you're still having Chrome issues after deployment

echo "Fixing Chrome for headless server operation..."

# Remove any corrupted Chrome processes
pkill -f chrome
pkill -f chromium

# Clear Chrome temp files
rm -rf /tmp/.com.google.Chrome.*
rm -rf /tmp/.org.chromium.Chromium.*

# Create Chrome data directory with proper permissions
mkdir -p /home/carolina-scraper/.config/google-chrome
chown -R carolina-scraper:carolina-scraper /home/carolina-scraper/.config

# Set memory limits for Chrome
echo "chrome soft nofile 65536" >> /etc/security/limits.conf
echo "chrome hard nofile 65536" >> /etc/security/limits.conf

# Install missing libraries if needed
apt-get update
apt-get install -y \
    libglib2.0-0 \
    libnss3-dev \
    libgdk-pixbuf2.0-dev \
    libgtk-3-dev \
    libxss-dev \
    libasound2-dev

# Test Chrome installation
echo "Testing Chrome installation..."
sudo -u carolina-scraper google-chrome-stable --headless --no-sandbox --disable-gpu --dump-dom https://www.google.com > /dev/null 2>&1

if [ $? -eq 0 ]; then
    echo "Chrome is working correctly!"
else
    echo "Chrome test failed. You may need to check the logs."
fi

echo "Chrome fix script completed."