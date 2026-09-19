# AGENTS.md

This file provides guidance to Codex (Codex.ai/code) when working with code in this repository.

## Before changing anything

Read `WORKFLOW.md` in this repo. It documents how changes are committed,
deployed to the web server, and verified, plus the standing gotchas
(SSH rate limiting, theatre-local vs UTC time, never writing to the
ticketing system). Follow it rather than inventing a new process.

## Common Commands

**Setup Environment:**
```bash
# Activate virtual environment
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

**Run Scraper Pipeline:**
```bash
# Step 1: Scrape movie data from Carolina Theatre website
python movie_scraper.py

# Step 2: Generate HTML website from scraped data
python site_generator.py

# Optional: Generate JSON data from database
python json_generator.py
```

## Architecture Overview

This is a Python-based web scraping and HTML generation system with three main components:

1. **Data Collection (`movie_scraper.py`)**: Uses Selenium WebDriver to scrape movie showtimes from Carolina Theatre website, stores in SQLite database with CSV backup
2. **HTML Generation (`site_generator.py`)**: Reads from SQLite database and generates index.html plus supporting pages (daily-cinema.html, about.html) with retro video game styling
3. **JSON Export (`json_generator.py`)**: Exports database content to structured JSON format

**Data Flow:**
- Web scraping → SQLite database (`movie_showtimes.db`) → HTML/JSON output
- Database schema: `showtimes` table with title, date, time, formatted_datetime, cinema, link, created_at
- All datetime handling uses standardized YYYY-MM-DD HH:MM format internally

**Key Dependencies:**
- Selenium + Chrome WebDriver for scraping
- BeautifulSoup for HTML parsing  
- SQLite for data persistence
- Custom datetime parsing with dateutil

The system handles various date formats ("Today", "Tomorrow", "Fri, May 30") and converts them to standardized datetime for consistent sorting and display.

## Design Principles for UI/UX Work

When working on the HTML generation or website styling (`site_generator.py`, `template.html`, `styles.css`), follow these design principles:

**Visual Hierarchy:**
- Movie titles should be most prominent (larger font, bold)
- Showtimes should be secondary but clearly readable
- Cinema/screen info should be tertiary
- Use size, color, and positioning to guide user attention to most important information

**Simplified User Experience:**
- Apply Hick's Law: minimize choices and remove unnecessary options
- Use Occam's Razor: keep design simple and focused on essential movie information
- Avoid visual clutter that distracts from core purpose (finding showtimes)

**Layout and Spacing:**
- Use Golden Ratio (1.618) for layout proportions when possible
- Apply Rule of Thirds for key element placement
- Implement generous white space for improved readability
- Group related showtimes using Gestalt proximity principles

**Interaction Design:**
- Apply Fitt's Law: make clickable elements (movie links) large and easy to target
- Ensure adequate spacing between interactive elements
- Prioritize mobile-responsive touch targets

**Content Organization:**
- Group movies logically (by date, then by time)
- Use consistent spacing and alignment
- Maintain visual consistency across all generated pages