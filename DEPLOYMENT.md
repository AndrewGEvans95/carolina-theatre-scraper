# Ubuntu Server Deployment Guide

## Quick Setup

1. **Deploy the application:**
   ```bash
   sudo bash deploy.sh
   ```

2. **Set up automated updates:**
   ```bash
   sudo bash setup_cron.sh
   ```

3. **Access your website:**
   - HTML Schedule: `https://carolinashowtimes.com`
   - JSON API: `https://carolinashowtimes.com/showtimes.json`

## What the deployment does:

- Installs all system dependencies (Python, Chrome)
- Creates dedicated user account (`carolina-scraper`)
- Sets up application in `/opt/carolina-theatre-scraper/`
- Uses existing nginx configuration
- Sets up logging and log rotation
- Runs initial test to verify everything works

## Cron Schedule

The scraper runs every 6 hours automatically:
- 12:00 AM
- 6:00 AM  
- 12:00 PM
- 6:00 PM

## Management Commands

```bash
# Manual run
sudo /opt/carolina-theatre-scraper/manual_run.sh

# View logs
tail -f /var/log/carolina-scraper/*.log

# Check cron jobs
sudo -u carolina-scraper crontab -l

# Check service status
sudo systemctl status cron
```

## File Locations

- Application: `/opt/carolina-theatre-scraper/`
- Website: `/var/www/html/index.html`
- JSON API: `/var/www/html/showtimes.json`
- Logs: `/var/log/carolina-scraper/`
- Database: `/opt/carolina-theatre-scraper/movie_showtimes.db`

## Troubleshooting

**Check logs for errors:**
```bash
ls -la /var/log/carolina-scraper/
tail -20 /var/log/carolina-scraper/scraper-*.log
```

**Test scraper manually:**
```bash
sudo /opt/carolina-theatre-scraper/manual_run.sh
```

**Chrome crashes or "tab crashed" errors:**
```bash
sudo bash /opt/carolina-theatre-scraper/fix_chrome.sh
```

**Permission errors with /var/www/html:**
```bash
sudo bash /opt/carolina-theatre-scraper/fix_permissions.sh
```

**Verify cron is running:**
```bash
sudo systemctl status cron
sudo -u carolina-scraper crontab -l
```

**Test Chrome directly:**
```bash
sudo -u carolina-scraper google-chrome-stable --headless --no-sandbox --disable-gpu --dump-dom https://www.google.com
```