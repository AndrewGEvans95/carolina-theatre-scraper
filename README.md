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

After scraping showtimes, `movie_scraper.py` records how full each showing is.

The theatre sells through Agile Ticketing, whose seat-map page exposes the
total seat count and marks each available seat, so for reserved-seating rooms
we can work out the percentage still for sale:

```
seats_available / seats_total  ->  % remaining      (the rest is unavailable)
```

Notes:

- Only showings sold with reserved seating publish a seat map, which is a
  per-showing choice rather than a property of the room: first-run films are
  usually reserved, repertory titles are often general admission even in the
  same cinema. General admission showings are recorded as
  `general_admission` with no numbers, since their quantity dropdown is a
  per-order purchase limit rather than remaining stock. In a recent check,
  37 of 61 upcoming showings had seat counts.
- "Unavailable" is not strictly "sold" - it also covers comps and seats the
  theatre holds back.
- Only showings starting within the next 14 days are checked, and each check
  is a single page load with a short pause between them.
- Readings are appended to the `availability` table rather than overwritten,
  so a showing's sales can be compared over time.

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
- `status` - `reserved`, `general_admission`, `multi_section`, or `no_data`
- `seats_total`, `seats_available` - set for `reserved` showings only

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