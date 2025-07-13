from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from bs4 import BeautifulSoup
import requests
import concurrent.futures
import csv
import sqlite3
from datetime import datetime, timedelta
import re
from dateutil import parser

def format_datetime(date_str, time_str):
    """
    Parse and format date and time strings to a standard format
    Returns formatted datetime string in YYYY-MM-DD HH:MM format
    
    Expected input formats:
    - Date: "Fri, May 30", "Sat, May 31", etc.
    - Time: "2:00pm", "1:10pm", "9:20pm", etc.
    """
    try:
        # Handle empty strings
        if not date_str or not time_str:
            return ""
        
        # Clean up the strings
        date_str = date_str.strip()
        time_str = time_str.strip()
        
        # Handle relative dates like "Today", "Tomorrow"
        today = datetime.now().date()
        current_year = datetime.now().year
        
        if "today" in date_str.lower():
            parsed_date = today
        elif "tomorrow" in date_str.lower():
            parsed_date = today + timedelta(days=1)
        else:
            # Handle format like "Fri, May 30" - need to add year
            try:
                # Remove day of week if present (e.g., "Fri, May 30" -> "May 30")
                if "," in date_str:
                    date_without_dow = date_str.split(", ", 1)[1]
                else:
                    date_without_dow = date_str
                
                # Add current year to the date string
                date_with_year = f"{date_without_dow}, {current_year}"
                
                # Parse the date
                parsed_date = parser.parse(date_with_year).date()
                
                # If the parsed date is in the past, assume it's next year
                if parsed_date < today:
                    date_with_year = f"{date_without_dow}, {current_year + 1}"
                    parsed_date = parser.parse(date_with_year).date()
                    
            except Exception as e:
                print(f"Warning: Could not parse date '{date_str}': {e}")
                return f"{date_str} {time_str}"
        
        # Parse time string (e.g., "2:00pm", "1:10pm")
        try:
            # Normalize the time format by adding space before am/pm if not present
            time_normalized = re.sub(r'(\d+:\d+)([ap]m)', r'\1 \2', time_str.lower())
            parsed_time = parser.parse(time_normalized).time()
        except Exception as e:
            # Manual parsing for time formats like "2:00pm"
            time_match = re.search(r'(\d{1,2}):(\d{2})\s*([ap]m)?', time_str.lower())
            if time_match:
                hour, minute, ampm = time_match.groups()
                hour = int(hour)
                minute = int(minute)
                
                if ampm:
                    if ampm == 'pm' and hour != 12:
                        hour += 12
                    elif ampm == 'am' and hour == 12:
                        hour = 0
                
                parsed_time = datetime.strptime(f"{hour:02d}:{minute:02d}", "%H:%M").time()
            else:
                print(f"Warning: Could not parse time '{time_str}': {e}")
                return f"{date_str} {time_str}"
        
        # Combine date and time
        combined_datetime = datetime.combine(parsed_date, parsed_time)
        
        # Return in standard format: YYYY-MM-DD HH:MM
        return combined_datetime.strftime("%Y-%m-%d %H:%M")
        
    except Exception as e:
        print(f"Warning: Could not parse datetime '{date_str} {time_str}': {e}")
        return f"{date_str} {time_str}"  # Return original if anything fails

def get_movie_links():
    urls = [
        "https://carolinatheatre.org/wp-admin/admin-ajax.php?action=film_filter&events=now-playing",
        "https://carolinatheatre.org/wp-admin/admin-ajax.php?action=film_filter&events=coming-soon"
    ]
    
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")  # Run Chrome in the background
    options.add_argument("--no-sandbox")  # Bypass OS security model
    options.add_argument("--disable-dev-shm-usage")  # Overcome limited resource problems
    options.add_argument("--disable-gpu")  # Disable GPU acceleration
    options.add_argument("--disable-extensions")  # Disable extensions
    options.add_argument("--disable-plugins")  # Disable plugins
    options.add_argument("--disable-images")  # Don't load images
    options.add_argument("--remote-debugging-port=9222")  # Enable remote debugging
    options.add_argument("--window-size=1920,1080")  # Set window size
    options.add_argument("--user-agent=Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36")
    movie_links = []
    
    for url in urls:
        driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)
        driver.get(url)
        page_source = driver.page_source
        driver.quit()
        
        soup = BeautifulSoup(page_source, "html.parser")
        for card in soup.select("div.card.eventCard.film"):  # Selector for movie cards
            title_elem = card.select_one("p.card__title")
            link_elem = card.select_one("a")
            
            title = title_elem.text.strip() if title_elem else ""
            link = link_elem["href"] if link_elem else ""
            
            if title and link and {"title": title, "link": link} not in movie_links:
                movie_links.append({"title": title, "link": link})
    
    return movie_links

def fetch_movie_showtimes(movie):
    """Fetch showtimes from an individual movie page"""
    response = requests.get(movie["link"], headers={"User-Agent": "Mozilla/5.0"})
    if response.status_code != 200:
        return []
    
    soup = BeautifulSoup(response.text, "html.parser")
    showtimes = []
    
    for date_elem in soup.select("li.showInfo__date"):
        date = date_elem.select_one(".date").text.strip() if date_elem.select_one(".date") else ""
        
        for time_elem in date_elem.select(".showInfo__times .time"):
            time_theater = time_elem.text.strip()
            
            if " - " in time_theater:
                time, cinema = time_theater.split(" - ", 1)
            else:
                time, cinema = time_theater, "Unknown Cinema"
            
            # Format the datetime to standard format
            formatted_datetime = format_datetime(date, time)
            
            showtime_entry = {
                "title": movie["title"],
                "date": date,  # Keep original date
                "time": time,  # Keep original time
                "formatted_datetime": formatted_datetime,  # Add formatted version
                "cinema": cinema,
                "link": movie["link"]
            }
            
            if showtime_entry not in showtimes:
                showtimes.append(showtime_entry)
    
    return showtimes

def create_database(db_name="movie_showtimes.db"):
    """Create database and showtimes table if they don't exist"""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    # Create table with appropriate schema
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS showtimes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            date TEXT NOT NULL,
            time TEXT NOT NULL,
            formatted_datetime TEXT,
            cinema TEXT,
            link TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(title, date, time, cinema, link)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Database '{db_name}' created/verified")

def save_to_database(showtimes, db_name="movie_showtimes.db"):
    """Save movie showtimes to SQLite database"""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    inserted_count = 0
    skipped_count = 0
    
    for showtime in showtimes:
        try:
            cursor.execute('''
                INSERT OR IGNORE INTO showtimes 
                (title, date, time, formatted_datetime, cinema, link)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (
                showtime["title"],
                showtime["date"],
                showtime["time"],
                showtime["formatted_datetime"],
                showtime["cinema"],
                showtime["link"]
            ))
            
            if cursor.rowcount > 0:
                inserted_count += 1
            else:
                skipped_count += 1
                
        except sqlite3.Error as e:
            print(f"Error inserting showtime: {e}")
    
    conn.commit()
    conn.close()
    
    print(f"Database updated: {inserted_count} new records inserted, {skipped_count} duplicates skipped")
    return inserted_count, skipped_count

def query_showtimes(db_name="movie_showtimes.db", movie_title=None, cinema=None, date_filter=None):
    """Query showtimes from database with optional filters"""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    query = "SELECT * FROM showtimes WHERE 1=1"
    params = []
    
    if movie_title:
        query += " AND title LIKE ?"
        params.append(f"%{movie_title}%")
    
    if cinema:
        query += " AND cinema LIKE ?"
        params.append(f"%{cinema}%")
    
    if date_filter:
        query += " AND date = ?"
        params.append(date_filter)
    
    query += " ORDER BY formatted_datetime"
    
    cursor.execute(query, params)
    results = cursor.fetchall()
    conn.close()
    
    return results

def export_to_csv_from_db(db_name="movie_showtimes.db", csv_filename="movie_showtimes_export.csv"):
    """Export database contents to CSV file"""
    conn = sqlite3.connect(db_name)
    cursor = conn.cursor()
    
    cursor.execute("SELECT title, date, time, formatted_datetime, cinema, link FROM showtimes ORDER BY formatted_datetime")
    results = cursor.fetchall()
    
    with open(csv_filename, "w", newline="", encoding="utf-8") as file:
        writer = csv.writer(file)
        writer.writerow(["Movie Title", "Date", "Time", "Formatted DateTime", "Cinema", "Link"])
        writer.writerows(results)
    
    conn.close()
    print(f"Database exported to {csv_filename}")

def get_movie_showtimes(movie_links):
    """Fetch showtimes concurrently for all movies"""
    showtimes = []
    
    with concurrent.futures.ThreadPoolExecutor() as executor:
        results = executor.map(fetch_movie_showtimes, movie_links)
        for result in results:
            for showtime in result:
                if showtime not in showtimes:
                    showtimes.append(showtime)
    
    return showtimes

if __name__ == "__main__":
    DB_NAME = "movie_showtimes.db"
    
    print("Setting up database...")
    create_database(DB_NAME)
    
    print("Fetching movie list...")
    movies = get_movie_links()
    print(f"Found {len(movies)} movies")
    
    print("Fetching showtimes...")
    movie_showtimes = get_movie_showtimes(movies)
    print(f"Found {len(movie_showtimes)} showtimes")
    
    print("Saving to database...")
    inserted, skipped = save_to_database(movie_showtimes, DB_NAME)
    
    # Optional: Export to CSV as backup
    print("Exporting to CSV...")
    export_to_csv_from_db(DB_NAME, "movie_showtimes.csv")
    
    # Optional: Show some sample queries
    print("\n--- Sample Database Queries ---")
    
    # Show all movies for today (if any)
    today_str = datetime.now().strftime("%a, %b %d").replace(" 0", " ")  # Format like "Fri, May 30"
    today_showtimes = query_showtimes(DB_NAME, date_filter=today_str)
    if today_showtimes:
        print(f"\nShowtimes for today ({today_str}):")
        for showtime in today_showtimes[:5]:  # Show first 5
            print(f"  {showtime[1]} - {showtime[2]} {showtime[3]} at {showtime[5]}")
    
    # Show Cinema One showtimes
    cinema_one_showtimes = query_showtimes(DB_NAME, cinema="Cinema One")
    if cinema_one_showtimes:
        print(f"\nCinema One showtimes (first 5):")
        for showtime in cinema_one_showtimes[:5]:
            print(f"  {showtime[1]} - {showtime[2]} {showtime[3]} at {showtime[4]}")
    
    print(f"\nComplete! Database: {DB_NAME}, CSV: movie_showtimes.csv")