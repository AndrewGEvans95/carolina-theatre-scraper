# Carolina Theatre Movie Scraper

A simple Python tool to scrape movie showtimes from the Carolina Theatre website and generate a clean, user-friendly HTML schedule.

## Features

- Scrapes current and upcoming movie showtimes from Carolina Theatre
- Stores data in SQLite database for persistence
- Generates a retro-styled HTML website with the schedule
- Supports filtering by date and grouping by movie
- Mobile-responsive design

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