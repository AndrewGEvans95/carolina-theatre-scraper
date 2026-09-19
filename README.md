# Carolina Theatre Movie Scraper

A simple Python tool to scrape movie showtimes from the Carolina Theatre website and generate a clean, user-friendly HTML schedule.

## Features

- Scrapes current and upcoming movie showtimes from Carolina Theatre
- Stores data in SQLite database for persistence
- Generates a retro-styled HTML website with the schedule
- Supports filtering by date and grouping by movie
- Mobile-responsive design

## Contributing

Changes go through a branch, a PR, then `./deploy.sh`. See
[WORKFLOW.md](WORKFLOW.md) for the exact sequence, the SSH rules for the
server, and the verification steps - read it before your first change.

## Setup

### 1. Clone the repository
```bash
git clone https://github.com/yourusername/carolina-theatre-scraper.git
cd carolina-theatre-scraper
```

### 2. Create and activate virtual environment
```bash
# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

## Usage

### Step 1: Scrape Movie Data
Run the scraper to fetch current showtimes and store them in a database:

```bash
python movie_scraper.py
```

This will:
- Create a SQLite database (`movie_showtimes.db`)
- Fetch movie listings and showtimes
- Export data to CSV as backup

### Step 2: Generate Website
Generate the HTML website from the scraped data:

```bash
python site_generator.py
```

This will create `index.html` with a clean, organized view of all showtimes.

You can also specify a custom output path:
```bash
python site_generator.py /path/to/output.html
```

## Files

- `movie_scraper.py` - Main scraper that fetches showtimes from Carolina Theatre website
- `availability.py` - Reads how many seats each upcoming showing has left
- `power_generator.py` - Builds the power dashboard (`power.html` + `power.json`)
- `site_generator.py` - Generates HTML website from the database
- `requirements.txt` - Python dependencies
- `movie_showtimes.db` - SQLite database (created after first run)
- `movie_showtimes.csv` - CSV backup (created after first run)

## Seat Availability

After scraping showtimes, `movie_scraper.py` records how full each showing
is, using the theatre's Agile Ticketing Sales API. One request returns every
showing in the window with its inventory:

```
AvailableInventory / TotalInventory  ->  % still for sale
SoldInventory                        ->  tickets actually bought
HoldInventory                        ->  seats the theatre is holding back
```

Notes:

- Covers **general admission and reserved seating alike**, which scraping
  the seat maps could not: GA showings have no seat map.
- `SoldInventory` is real sales, so "sold" no longer has to be inferred from
  what is left over. Available + sold + held equals capacity exactly.
- Only showings starting within the next 14 days are recorded.
- Readings are appended to the `availability` table rather than overwritten,
  so a showing's sales can be compared over time.

### Credentials

The API needs keys, which are **not** in this repository. Provide them via
the environment or a `key=value` file at one of:

```
.env                                  (local development; git-ignored)
/etc/carolina-scraper/api.env         (the server)
~/.config/carolina-scraper/api.env
```

```
AGILE_APP_KEY=...
AGILE_USER_KEY=...
AGILE_CORP_ORG_ID=...
AGILE_BUYER_TYPE_ID=1816    # optional; public web buyer type
AGILE_API_BASE=...          # optional; defaults to prod3
```

Without credentials the availability step is skipped and everything else
works as normal.

### Checking by hand

```bash
python availability.py --list              # every upcoming showing
python availability.py --showing 1034337   # one showing, raw API response
python availability.py --bulk              # record into the database
```

## Power Dashboard

`power.html` is a separate page for people who want the numbers rather than
a showtime. It lists every showing in the next 14 days with:

- inventory: sold, left, held, total, and a fill bar
- pricing: list price, charged price and the fee between them
- seating mode (GA or reserved), order limits, and whether the theatre
  hides its remaining quantity on the public site
- freshness (when it was last checked), how many tickets sold in the last
  6 and 24 hours, and a trend line of the last week of readings, once
  there is enough snapshot history to say

Column headings are grouped (Seats / Price per ticket / Tickets sold) and a
legend under the table defines each one, so "Face" and "At checkout" don't
have to be guessed at.

Filters for date, room and seating mode, and sorting by start time, fill,
sold, seats left, price or 24h velocity.

Each showing's raw readings are included as `sold_history`. **Currently private.** The page is generated to
`/opt/carolina-theatre-scraper/private/` on the server, which Apache does
not serve, and is not linked from the site. To read it:

```bash
./view_power.sh              # fetch it and open it in a browser
./view_power.sh ~/dashboards # or keep the copy somewhere
```

That directory is self-contained (the page, its stylesheet and
`power.json`), so the copy renders exactly as the published version would.
To build one from local data instead: `python power_generator.py -o .`

The same data is written beside it as `power.json`, so it can be consumed
without scraping the page. Held seats are kept back by the theatre: neither
sold nor for sale, which is why sold + left rarely equals capacity.

Velocity shows a dash until two snapshots exist far enough apart - it is
never inferred from a single reading.

Deploying only generator or template changes? `./deploy.sh --no-scrape`
rebuilds the pages from the data already on the server instead of
re-fetching every film page.

```bash
python power_generator.py -o .        # power.html + power.json here
python power_generator.py --days 30   # a longer window
```

## Database Schema

The SQLite database contains a `showtimes` table with:
- `title` - Movie title
- `date` - Original date string
- `time` - Original time string  
- `formatted_datetime` - Standardized datetime format
- `cinema` - Theater/screen name
- `link` - Link to movie details
- `created_at` - Timestamp of record creation
- `showing_id` - Agile Ticketing showing id, used to look up availability

And an `availability` table, one row per check:
- `showing_id`, `checked_at` - which showing, and when it was read
- `status` - `reserved` or `general_admission`
- `seats_total`, `seats_available`, `seats_sold`, `seats_held` - capacity,
  what's left, what sold, and what the theatre is holding back

## Requirements

- Python 3.7+
- Chrome browser (for Selenium)
- Internet connection

## Notes

- The scraper uses Selenium with Chrome in headless mode
- ChromeDriver is automatically managed by webdriver-manager
- First run may take longer as ChromeDriver downloads
- Website generation works offline using the local database

## Troubleshooting

**Chrome/ChromeDriver Issues:**
- Ensure Chrome browser is installed
- ChromeDriver will download automatically on first run

**Permission Issues (Linux/Mac):**
- For web server deployment: `sudo python site_generator.py`
- Or specify local output: `python site_generator.py ./website.html`

**Database Issues:**
- Delete `movie_showtimes.db` and re-run scraper to reset
- Check that the Carolina Theatre website structure hasn't changed

## License

MIT License - Feel free to modify and distribute.

---

*Built with noble wrath and unwavering purpose by Andrew Evans aka lilcrisp*