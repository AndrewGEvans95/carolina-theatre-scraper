import argparse
import sqlite3
import re
import os
import shutil
import textwrap

from collections import defaultdict
from datetime import datetime, timedelta

def slugify(title):
    """
    Convert a string (movie title) into a URL-friendly slug.
    """
    slug = re.sub(r'[^\w\s-]', '', title.lower()).strip()
    slug = re.sub(r'[\s]+', '-', slug)
    return slug

def parse_time_from_formatted_datetime(formatted_datetime):
    """
    Extract time from the formatted datetime string for sorting.
    Input: "2025-05-30 14:00" -> Returns datetime object for sorting
    """
    try:
        return datetime.strptime(formatted_datetime, "%Y-%m-%d %H:%M")
    except (ValueError, TypeError):
        # Fallback: try to parse just the time portion if available
        try:
            time_part = formatted_datetime.split()[-1] if formatted_datetime else "00:00"
            return datetime.strptime(f"2025-01-01 {time_part}", "%Y-%m-%d %H:%M")
        except:
            return datetime.strptime("2025-01-01 00:00", "%Y-%m-%d %H:%M")

def format_date_for_display(formatted_datetime):
    """
    Convert formatted datetime back to display format for UI compatibility.
    Input: "2025-05-30 14:00" -> Output: "Fri, May 30"
    """
    try:
        dt = datetime.strptime(formatted_datetime, "%Y-%m-%d %H:%M")
        return dt.strftime("%a, %b %d").replace(" 0", " ")  # Remove leading zero from day
    except (ValueError, TypeError):
        return "Unknown Date"

def format_time_for_display(formatted_datetime):
    """
    Convert formatted datetime back to 12-hour time format for UI compatibility.
    Input: "2025-05-30 14:00" -> Output: "2:00pm"
    """
    try:
        dt = datetime.strptime(formatted_datetime, "%Y-%m-%d %H:%M")
        return dt.strftime("%I:%M%p").lower().lstrip('0')  # Remove leading zero and make lowercase
    except (ValueError, TypeError):
        return "Unknown Time"

def get_showtimes_from_database(db_name="movie_showtimes.db"):
    """
    Retrieve showtimes from the database and return them in the format expected by the HTML generator.
    """
    try:
        conn = sqlite3.connect(db_name)
        cursor = conn.cursor()
        
        # Query all showtimes, ordered by formatted datetime for proper chronological order
        cursor.execute("""
            SELECT title, date, time, formatted_datetime, cinema, link 
            FROM showtimes 
            WHERE formatted_datetime IS NOT NULL 
            ORDER BY formatted_datetime
        """)
        
        results = cursor.fetchall()
        conn.close()
        
        # Convert to list of dictionaries
        showtimes = []
        for row in results:
            title, original_date, original_time, formatted_datetime, cinema, link = row
            
            # Use original date/time if available, otherwise derive from formatted_datetime
            display_date = original_date if original_date else format_date_for_display(formatted_datetime)
            display_time = original_time if original_time else format_time_for_display(formatted_datetime)
            
            showtimes.append({
                "Movie Title": title,
                "Date": display_date,
                "Time": display_time,
                "Formatted DateTime": formatted_datetime,
                "Cinema": cinema,
                "Link": link
            })
        
        return showtimes
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    except Exception as e:
        print(f"Error reading from database: {e}")
        return []

def load_template(template_file="template.html"):
    """
    Load HTML template from file.
    """
    try:
        with open(template_file, "r", encoding="utf-8") as file:
            return file.read()
    except FileNotFoundError:
        print(f"Error: Template file '{template_file}' not found!")
        return None
    except Exception as e:
        print(f"Error reading template file: {str(e)}")
        return None

def reindent(text, length):
    return textwrap.indent(textwrap.dedent(text), " " * length)

def generate_html(db_name="movie_showtimes.db", 
                  output_html_file=None, 
                  template_file="template.html", 
                  backup=True):
    # Define the output path with better defaults
    if output_html_file is None:
        # Try web directory first, then fall back to local
        if os.path.exists("/var/www/html") and os.access("/var/www/html", os.W_OK):
            output_path = "/var/www/html/index.html"
        else:
            # Fall back to current directory
            output_path = "./index.html"
            print(f"Cannot write to /var/www/html (requires sudo)")
            print(f"Writing to current directory instead: {output_path}")
    else:
        output_path = output_html_file
    
    # Check if we have write permissions for the chosen path
    output_dir = os.path.dirname(output_path) or "."
    if not os.access(output_dir, os.W_OK):
        print(f"Error: No write permission for {output_dir} directory")
        if "/var/www/html" in output_path:
            print("Try running with sudo: sudo python site_generator.py")
            print("Or specify a different output path")
        return False
    
    if backup:
      # Create backup of existing file if it exists
      if os.path.exists(output_path):
          backup_path = f"{output_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
          try:
              shutil.copy2(output_path, backup_path)
              print(f"Created backup: {backup_path}")
          except Exception as e:
              print(f"Warning: Could not create backup: {str(e)}")
              # Continue anyway since this is not critical

    # Load template
    template_content = load_template(template_file)
    if template_content is None:
        return False

    showtimes_by_date = defaultdict(list)

    # Get showtimes from database instead of CSV
    print("Reading showtimes from database...")
    try:
        showtimes_data = get_showtimes_from_database(db_name)
        if not showtimes_data:
            print("No showtimes found in database")
            return False
            
        print(f"Found {len(showtimes_data)} showtimes in database")
        
    except Exception as e:
        print(f"Error reading from database: {str(e)}")
        return False

    # Group showtimes by date, using formatted datetime for proper sorting
    for row in showtimes_data:
        title = row["Movie Title"].strip()
        date_str = row["Date"].strip()
        time_str = row["Time"].strip()
        formatted_datetime = row["Formatted DateTime"]
        cinema = row["Cinema"].strip()
        link = row["Link"].strip()
        
        # For grouping, we'll use the display date with year added for consistency
        # If the date doesn't already have a year, add the current year
        if ", 2025" not in date_str and ", 2024" not in date_str:
            # Determine year from formatted datetime
            try:
                dt = datetime.strptime(formatted_datetime, "%Y-%m-%d %H:%M")
                date_with_year = f"{date_str}, {dt.year}"
            except:
                date_with_year = f"{date_str}, 2025"  # Default fallback
        else:
            date_with_year = date_str
        
        showtimes_by_date[date_with_year].append({
            "title": title,
            "time": time_str,
            "cinema": cinema,
            "link": link,
            "formatted_datetime": formatted_datetime  # Keep for sorting
        })

    # Sort each day's movies by formatted datetime instead of parsed time
    for date in showtimes_by_date:
        showtimes_by_date[date].sort(key=lambda x: parse_time_from_formatted_datetime(x.get("formatted_datetime", "")))
    
    # Get today's date (only the date part)
    today = datetime.today().date()
    
    # Create a sorted list of dates (as strings) that are today or in the future.
    # Use formatted datetime to determine if date is in future
    future_dates = []
    for date_str in showtimes_by_date.keys():
        try:
            # Parse the date string to check if it's in the future
            parsed_date = datetime.strptime(date_str, "%a, %b %d, %Y").date()
            if parsed_date >= today:
                future_dates.append(date_str)
        except ValueError:
            # If parsing fails, include it anyway
            future_dates.append(date_str)
    
    sorted_dates = sorted(
        future_dates,
        key=lambda d: datetime.strptime(d, "%a, %b %d, %Y")
    )
    
    # Use all dates together (removing any festival split)
    schedule_showtimes_by_date = {d: showtimes_by_date[d] for d in sorted_dates}
    
    # Build day filter options
    day_filter_options = ""
    for date in sorted_dates:
        day_filter_options += (
            f"""<option value="{date}">{date}</option>
            """
        )
    
    # Build schedule content
    schedule_content = ""
    
    # Output movies grouped by day (as before) and also grouped by movie (new).
    movie_counter = 1
    for date in sorted_dates:
        schedule_content += (
            f"""
            <div class='day' data-date='{date}'>
              <h2>{date}</h2>
            """
        )
        for movie in schedule_showtimes_by_date[date]:
            # Create a unique movie ID based on the title slug and counter.
            movie_slug = slugify(movie['title'])
            movie_id = f"movie-{movie_slug}-{movie_counter}"
            formatted_datetime = movie.get('formatted_datetime', '')
            schedule_content += (
              f"""
              <div class='movie' id='{movie_id}' data-movie-title='{movie['title']}' data-movie-time='"{movie['time']}' data-movie-date='{date}' data-movie-cinema='{movie['cinema']}' data-formatted-datetime='{formatted_datetime}'>
                <span class='movie-title'><a href='{movie['link']}' target='_blank'>{movie['title']}</a></span>
                <div class='movie-info'>
                  <span class='movie-time'>{movie['time']}</span>
                  <span class='movie-cinema'>{movie['cinema']}</span>
                  <button class='other-times-btn' onclick="showOtherTimes('{movie['title']}', '{movie['time']}', '{date}', '{movie['cinema']}', '{movie_id}')">Show Other Times</button>
                  <button class='share-btn' onclick='copyShareLink("{movie_id}", event)' title='Copy link'>Copy Link</button>
                </div>
              </div>
              """
            )
            movie_counter += 1
        schedule_content += """
            </div>
        """
    
    # Group movies by movie (new) (using a new div with class 'movie-group' and a h3 for the movie title).
    movie_groups = {}
    seen_showtimes = set()  # Track unique showtimes to prevent duplicates
    for date in sorted_dates:
        for movie in schedule_showtimes_by_date[date]:
            title = movie['title']
            # Create a unique key for this showtime
            showtime_key = f"{title}|{movie['time']}|{date}|{movie['cinema']}"
            if showtime_key not in seen_showtimes:
                seen_showtimes.add(showtime_key)
                if title not in movie_groups:
                    movie_groups[title] = []
                movie_groups[title].append({**movie, 'display_date': date})
    
    for (title, movies) in sorted(movie_groups.items()):
        schedule_content += (
            f"""
            <div class='movie-group' style='display:none;'>
              <h3>{title}</h3>
            """)
      
        for movie in movies:
            movie_slug = slugify(movie['title'])
            movie_id = f"movie-{movie_slug}-{movie_counter}"
            # Append the day (date) (e.g. "(Fri, Feb 28)") so that the user can see on which day the movie is playing.
            day_str = movie.get("display_date", "").strip()
            formatted_datetime = movie.get('formatted_datetime', '')
            schedule_content += (
              f"""
              <div class='movie' id='{movie_id}' data-movie-title='{movie['title']}' data-movie-time='{movie['time']}' data-movie-date='{day_str}' data-movie-cinema='{movie['cinema']}' data-formatted-datetime='{formatted_datetime}'>"
              <span class='movie-title'><a href='{movie['link']}' target='_blank'>{movie['title']}</a></span>
                "<div class='movie-info'>"
                  <span class='movie-time'>{movie['time']} ({day_str})</span>
                  <span class='movie-cinema'>{movie['cinema']}</span>
                  <button class='other-times-btn' onclick="showOtherTimes('{movie['title']}', '{movie['time']}', '{day_str}', '{movie['cinema']}', '{movie_id}')">Show Other Times</button>
                  <button class='share-btn' onclick='copyShareLink("{movie_id}", event)' title='Copy link'>Copy Link</button>
                </div>
              </div>
              """
            )
            movie_counter += 1
        schedule_content += """
            </div>
        """
    
    schedule_content = reindent(schedule_content, 5)
    
    # Replace template variables with actual content
    html_content = template_content.replace('{{DAY_FILTER_OPTIONS}}', day_filter_options)
    html_content = html_content.replace('{{SCHEDULE_CONTENT}}', schedule_content)
    
    # Copy CSS file to output directory
    css_source = "styles.css"
    if os.path.exists(css_source):
        output_dir = os.path.dirname(output_path) or "."
        css_dest = os.path.join(output_dir, "styles.css")
        try:
            shutil.copy2(css_source, css_dest)
            print(f"CSS file copied to: {css_dest}")
        except Exception as e:
            print(f"Warning: Could not copy CSS file: {str(e)}")
    else:
        print(f"Warning: CSS file '{css_source}' not found")

    # Copy additional HTML files to output directory
    additional_files = ["daily-cinema.html", "about.html", "truth.html", "drawing.png"]
    output_dir = os.path.dirname(output_path) or "."
    for filename in additional_files:
        if os.path.exists(filename):
            dest_path = os.path.join(output_dir, filename)
            try:
                shutil.copy2(filename, dest_path)
                print(f"Additional file copied to: {dest_path}")
            except Exception as e:
                print(f"Warning: Could not copy {filename}: {str(e)}")

    # Write the HTML file with error handling
    try:
        with open(output_path, "w", encoding="utf-8") as file:
            file.write(html_content)
        print(f"HTML file successfully saved to: {output_path}")
        return True
    except Exception as e:
        print(f"Error writing HTML file: {str(e)}")
        return False

if __name__ == "__main__":
    import sys
    
    DB_NAME = "movie_showtimes.db"
    
    # Check if database exists
    if not os.path.exists(DB_NAME):
        print(f"Error: Database file '{DB_NAME}' not found!")
        print("Make sure to run the movie scraper first to create the database")
        exit(1)

    parser = argparse.ArgumentParser(
        prog="site_generator.py",
        description="generates the static site from template.html",
    )

    parser.add_argument("-o", "--output-file")
    parser.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    
    # Allow user to specify output file as command line argument
    output_file = args.output_file
    if output_file:
        print(f"Using custom output file: {output_file}")

    backup = not args.no_backup 
    
    print("Generating Carolina Theatre website from database...")
    success = generate_html(DB_NAME, output_file, backup=backup)
    
    if not success:
        print("\nFailed to generate and deploy the website")
        print("\nSolutions:")
        print("   1. Run with sudo: sudo python site_generator.py")
        print("   2. Specify a local path: python site_generator.py ./website.html")
        print("   3. Use current directory: python site_generator.py")
        exit(1)
    
    print("Website successfully generated!")
    if output_file:
        if "/var/www/html" in output_file:
            print("Website deployed to web server")
        else:
            print(f"HTML file saved to: {output_file}")
    else:
        print("HTML file saved locally - you can now upload it to your web server")