# Deployment

The site runs on a DigitalOcean droplet (Ubuntu 22.04). SSH alias: `carolinashowtimes`.

## Deploying changes

Merge to `main` on GitHub, then from your machine:

```bash
./deploy.sh
```

This opens one SSH connection and, on the server:
1. `git pull --ff-only origin main` in `/opt/carolina-theatre-scraper` (as `carolina-scraper`)
2. `pip install -r requirements.txt` into the app venv
3. Runs `manual_run.sh` (scrape + regenerate the site) so the change is live immediately

Only `main` is deployed. Don't edit files in `/opt` directly — the next pull will refuse to run until those edits are removed.

## How it runs

- **Code:** `/opt/carolina-theatre-scraper` — git checkout owned by `carolina-scraper`
- **Schedule:** `carolina-scraper`'s crontab runs `run_scraper.sh` every 6 hours (00:00, 06:00, 12:00, 18:00 UTC)
- **Pipeline:** `movie_scraper.py` (headless Chrome) → `movie_showtimes.db` → `site_generator.py -o /var/www/html/index.html`
- **Web server:** Apache 2.4 serves `/var/www/html`; HTTPS via Let's Encrypt (certbot)
- **Database:** `/opt/carolina-theatre-scraper/movie_showtimes.db` — not in git; back it up before risky changes
- **Logs:** `/var/log/carolina-scraper/`

## Management

```bash
# Run the pipeline now
ssh carolinashowtimes /opt/carolina-theatre-scraper/manual_run.sh

# Latest log
ssh carolinashowtimes 'tail -40 "$(ls -t /var/log/carolina-scraper/*.log | head -1)"'

# Cron entry
ssh carolinashowtimes 'crontab -l -u carolina-scraper'
```

The server's firewall rate-limits SSH (ufw `LIMIT`): more than ~6 connections in 30 seconds blocks your IP briefly. Batch commands into one `ssh` call.

## Setting up a new server

On a fresh Ubuntu server, as root:

```bash
git clone https://github.com/AndrewGEvans95/carolina-theatre-scraper.git /tmp/cts
cd /tmp/cts
sudo bash provision.sh   # user, Chrome, venv, logrotate, test run
sudo bash setup_cron.sh  # 6-hourly cron job
```

Apache and certbot are configured separately.

## Troubleshooting

**Chrome crashes or "tab crashed" errors:**
```bash
sudo bash /opt/carolina-theatre-scraper/fix_chrome.sh
```

**Permission errors with /var/www/html:**
```bash
sudo bash /opt/carolina-theatre-scraper/fix_permissions.sh
```

**Test Chrome directly:**
```bash
sudo -u carolina-scraper google-chrome-stable --headless --no-sandbox --disable-gpu --dump-dom https://www.google.com
```
