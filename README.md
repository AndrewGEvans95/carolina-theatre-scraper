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

This will create `carolina_theatre_schedule.html` with a clean, organized view of all showtimes.

You can also specify a custom output path:
```bash
python site_generator.py /path/to/output.html
```

## Files

- `movie_scraper.py` - Main scraper that fetches showtimes from Carolina Theatre website
- `site_generator.py` - Generates HTML website from the database
- `requirements.txt` - Python dependencies
- `movie_showtimes.db` - SQLite database (created after first run)
- `movie_showtimes.csv` - CSV backup (created after first run)

## Database Schema

The SQLite database contains a `showtimes` table with:
- `title` - Movie title
- `date` - Original date string
- `time` - Original time string  
- `formatted_datetime` - Standardized datetime format
- `cinema` - Theater/screen name
- `link` - Link to movie details
- `created_at` - Timestamp of record creation

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