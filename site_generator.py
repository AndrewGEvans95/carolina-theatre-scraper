import sqlite3
import re
import os
import shutil
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

def generate_html(db_name="movie_showtimes.db", output_html_file=None):
    # Define the output path with better defaults
    if output_html_file is None:
        # Try web directory first, then fall back to local
        if os.path.exists("/var/www/html") and os.access("/var/www/html", os.W_OK):
            output_path = "/var/www/html/index.html"
        else:
            # Fall back to current directory
            output_path = "./carolina_theatre_schedule.html"
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
    
    # Create backup of existing file if it exists
    if os.path.exists(output_path):
        backup_path = f"{output_path}.backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        try:
            shutil.copy2(output_path, backup_path)
            print(f"Created backup: {backup_path}")
        except Exception as e:
            print(f"Warning: Could not create backup: {str(e)}")
            # Continue anyway since this is not critical

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
    
    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Carolina Theatre Schedule</title>
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Press+Start+2P&display=swap');
    body {
      font-family: 'Press Start 2P', cursive, Arial, sans-serif;
      background: linear-gradient(135deg, #0f2027 0%, #2c5364 100%);
      color: #39ff14;
      text-shadow: 0 0 2px #39ff14, 0 0 4px #00fff7;
      text-align: center;
      padding: 20px;
      margin: 0;
      image-rendering: pixelated;
      min-height: 100vh;
      box-sizing: border-box;
      overflow-x: hidden;
    }
    .container {
      width: 95%;
      max-width: 960px;
      margin: 0 auto;
      background: rgba(20, 20, 40, 0.95);
      padding: 24px;
      border: 4px solid #ff0080;
      border-radius: 0;
      box-shadow: 0 0 24px #00fff7, 0 0 8px #ff0080 inset;
      box-sizing: border-box;
      overflow-x: hidden;
    }
    .tabs {
      display: flex;
      flex-wrap: wrap;
      justify-content: center;
      gap: 16px;
      margin-bottom: 24px;
    }
    .tab {
      padding: 12px 20px;
      background: #222;
      border: 2px solid #ff0080;
      border-radius: 0;
      color: #fff;
      font-family: 'Press Start 2P', cursive;
      font-size: 12px;
      font-weight: normal;
      cursor: pointer;
      box-shadow: 0 0 8px #00fff7;
      transition: background 0.2s, color 0.2s;
    }
    .tab:hover, .tab:focus {
      background: #ff0080;
      color: #39ff14;
      outline: none;
    }
    .tab-content {
      display: none;
    }
    .tab-content.active {
      display: block;
    }
    h1, h2 {
      color: #ff0080;
      text-shadow: 0 0 2px #00fff7;
      font-family: 'Press Start 2P', cursive;
      font-weight: normal;
    }
    .day {
      background: #111;
      border: 2px dashed #00fff7;
      padding: 18px;
      margin: 16px 0;
      text-align: left;
      box-shadow: 0 0 8px #00fff7 inset;
    }
    .movie {
      padding: 12px;
      font-size: 14px;
      color: #39ff14;
      display: flex;
      flex-wrap: nowrap;
      justify-content: space-between;
      align-items: center;
      border-bottom: 1px dotted #ff0080;
      font-family: 'Press Start 2P', cursive;
      font-weight: normal;
      gap: 8px;
    }
    .movie:last-child {
      border-bottom: none;
    }
    .movie-title {
      font-weight: normal;
      font-size: 16px;
      flex: 0 1 auto;
      text-shadow: 0 0 2px #00fff7;
      display: flex;
      align-items: center;
      gap: 8px;
      min-width: 0;
      max-width: 60%;
    }
    .movie-title a {
      color: #00fff7;
      text-decoration: none;
      font-weight: normal;
      transition: color 0.2s;
      overflow: hidden;
      text-overflow: ellipsis;
      white-space: nowrap;
    }
    .movie-title a:hover,
    .movie-title a:focus {
      color: #ff0080;
      text-decoration: underline;
    }
    .share-btn {
      background: #ff0080;
      color: #fff;
      border: none;
      border-radius: 0;
      font-family: 'Press Start 2P', cursive;
      font-size: 10px;
      cursor: pointer;
      padding: 2px 4px;
      box-shadow: 0 0 4px #00fff7;
      transition: all 0.2s;
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 24px;
      height: 24px;
      flex-shrink: 0;
    }
    .share-btn:hover {
      background: #39ff14;
      color: #000;
    }
    .share-btn.copied {
      background: #39ff14;
      color: #000;
    }
    .movie-info {
      display: flex;
      align-items: center;
      gap: 8px;
      flex: 0 0 auto;
      flex-wrap: nowrap;
    }
    .movie-time, .movie-cinema {
      flex: 0 0 auto;
      text-align: center;
      font-size: 12px;
      color: #fff;
      background: #222;
      border: 1px solid #00fff7;
      padding: 4px 8px;
      border-radius: 0;
      box-shadow: 0 0 4px #00fff7;
      white-space: nowrap;
    }
    .other-times-btn {
      flex: 0 0 auto;
      white-space: nowrap;
    }
    pre {
      text-align: center;
      background: #222;
      padding: 10px;
      border: 2px solid #ff0080;
      border-radius: 0;
      overflow-x: auto;
      color: #39ff14;
      font-family: 'Press Start 2P', cursive;
      font-weight: normal;
    }
    footer {
      margin-top: 2rem;
      font-style: italic;
      text-align: center;
      font-size: 0.9em;
      opacity: 0.8;
      color: #00fff7;
      text-shadow: 0 0 2px #ff0080;
    }
    @media (max-width: 767px) {
      body {
        padding: 10px;
        font-size: 12px;
      }
      .container {
        width: 100%;
        padding: 12px;
        margin: 0;
        border-width: 2px;
      }
      h1 {
        font-size: 18px;
        margin: 8px 0;
        word-wrap: break-word;
      }
      h2 {
        font-size: 14px;
        margin: 6px 0;
        word-wrap: break-word;
      }
      .tabs {
        gap: 4px;
        margin-bottom: 12px;
        flex-wrap: wrap;
      }
      .tab {
        padding: 6px 8px;
        font-size: 9px;
        flex: 1;
        min-width: 80px;
        text-align: center;
        white-space: nowrap;
        overflow: hidden;
        text-overflow: ellipsis;
      }
      .movie {
        padding: 8px;
        gap: 4px;
        font-size: 12px;
        flex-wrap: wrap;
      }
      .movie-title {
        max-width: calc(100% - 24px);
        font-size: 12px;
        min-width: 0;
      }
      .movie-title a {
        font-size: 12px;
        max-width: 100%;
      }
      .movie-info {
        width: 100%;
        display: flex;
        flex-wrap: nowrap;
        justify-content: flex-start;
        gap: 4px;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
        padding-bottom: 4px;
        margin-top: 4px;
      }
      .movie-time, .movie-cinema {
        font-size: 10px;
        padding: 3px 6px;
        flex: 0 0 auto;
        min-width: max-content;
      }
      .share-btn {
        font-size: 8px;
        padding: 2px 3px;
        min-width: 20px;
        height: 20px;
        position: absolute;
        right: 8px;
        top: 8px;
      }
      .other-times-btn {
        font-size: 10px;
        padding: 3px 6px;
        flex: 0 0 auto;
        min-width: max-content;
      }
      .day, .movie-group {
        padding: 8px;
        margin: 8px 0;
      }
      .filter {
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin-bottom: 12px;
        padding: 0 4px;
      }
      .filter select {
        width: 100%;
        padding: 6px;
        font-size: 10px;
        font-family: 'Press Start 2P', cursive;
      }
      .filter label {
        font-size: 10px;
        margin-bottom: 2px;
      }
      .other-times-dialog {
        width: 90%;
        max-width: none;
        padding: 12px;
        font-size: 11px;
        margin: 0 5%;
      }
      .other-times-dialog-title {
        font-size: 12px;
        margin-bottom: 8px;
        word-wrap: break-word;
      }
      .other-times-link {
        font-size: 11px;
        padding: 6px;
        margin: 3px 0;
        word-wrap: break-word;
      }
      .other-times-dialog button {
        width: 100%;
        margin-top: 8px;
        padding: 8px;
        font-size: 11px;
      }
      .glitch-button {
        width: 100%;
        margin: 12px 0;
        padding: 10px;
        font-size: 11px;
      }
      pre {
        font-size: 7px;
        padding: 6px;
        margin: 6px 0;
        overflow-x: auto;
        -webkit-overflow-scrolling: touch;
      }
      footer {
        font-size: 9px;
        margin-top: 12px;
        padding: 0 4px;
        word-wrap: break-word;
      }
    }
    /* Add styles for very small screens */
    @media (max-width: 360px) {
      body {
        padding: 5px;
        font-size: 10px;
      }
      .container {
        padding: 8px;
      }
      .movie-title {
        font-size: 11px;
      }
      .movie-time, .movie-cinema {
        font-size: 9px;
        padding: 2px 4px;
      }
      .other-times-btn {
        font-size: 9px;
        padding: 2px 4px;
      }
      .tab {
        font-size: 8px;
        padding: 4px 6px;
      }
    }
    /* New styles for the glitch button and dialog */
    .glitch-button {
      margin: 20px auto;
      padding: 10px 20px;
      background: #ff0080;
      color: #fff;
      border: none;
      border-radius: 0;
      font-family: 'Press Start 2P', cursive;
      font-size: 14px;
      cursor: pointer;
      box-shadow: 0 0 8px #00fff7;
      transition: all 0.2s;
    }
    .glitch-button:hover {
      background: #39ff14;
      color: #000;
    }
    .dialog {
      display: none;
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: #111;
      border: 2px solid #ff0080;
      padding: 20px;
      color: #39ff14;
      font-family: 'Press Start 2P', cursive;
      font-size: 14px;
      text-align: center;
      box-shadow: 0 0 24px #00fff7;
      z-index: 1000;
    }
    .dialog button {
      margin-top: 10px;
      padding: 8px 16px;
      background: #ff0080;
      color: #fff;
      border: none;
      border-radius: 0;
      font-family: 'Press Start 2P', cursive;
      font-size: 12px;
      cursor: pointer;
      box-shadow: 0 0 8px #00fff7;
    }
    .dialog button:hover {
      background: #39ff14;
      color: #000;
    }
    .glitch {
      animation: glitch 0.3s infinite;
    }
    @keyframes glitch {
      0% { transform: translate(0); }
      20% { transform: translate(-2px, 2px); }
      40% { transform: translate(-2px, -2px); }
      60% { transform: translate(2px, 2px); }
      80% { transform: translate(2px, -2px); }
      100% { transform: translate(0); }
    }
    /* New styles for movie grouping */
    .movie-group {
      background: #111;
      border: 2px dashed #00fff7;
      padding: 18px;
      margin: 16px 0;
      text-align: left;
      box-shadow: 0 0 8px #00fff7 inset;
    }
    .movie-group h3 {
      color: #ff0080;
      text-shadow: 0 0 2px #00fff7;
      font-family: 'Press Start 2P', cursive;
      font-weight: normal;
    }
    .other-times-dialog {
      display: none;
      position: fixed;
      top: 50%;
      left: 50%;
      transform: translate(-50%, -50%);
      background: #181830;
      border: 3px solid #00fff7;
      padding: 28px 32px 20px 32px;
      color: #39ff14;
      font-family: 'Press Start 2P', cursive;
      font-size: 15px;
      text-align: center;
      box-shadow: 0 0 32px #00fff7, 0 0 8px #ff0080 inset;
      z-index: 2000;
      min-width: 340px;
      border-radius: 8px;
    }
    .other-times-dialog-title {
      color: #ff0080;
      font-size: 16px;
      margin-bottom: 12px;
      text-shadow: 0 0 4px #00fff7;
    }
    .other-times-list {
      margin-bottom: 16px;
      text-align: left;
    }
    .other-times-link {
      display: block;
      color: #00fff7;
      background: #222;
      border: 1px solid #ff0080;
      border-radius: 4px;
      margin: 6px 0;
      padding: 8px 10px;
      text-decoration: none;
      font-size: 14px;
      font-family: 'Press Start 2P', cursive;
      transition: background 0.2s, color 0.2s, border 0.2s;
      box-shadow: 0 0 6px #00fff7;
    }
    .other-times-link:hover {
      background: #ff0080;
      color: #fff;
      border: 1px solid #00fff7;
    }
    .other-times-dialog button {
      margin-top: 10px;
      padding: 8px 16px;
      background: #ff0080;
      color: #fff;
      border: none;
      border-radius: 0;
      font-family: 'Press Start 2P', cursive;
      font-size: 12px;
      cursor: pointer;
      box-shadow: 0 0 8px #00fff7;
      transition: background 0.2s, color 0.2s;
    }
    .other-times-dialog button:hover {
      background: #39ff14;
      color: #000;
    }
    .share-btn.error {
      background: #ff0000;
      color: #fff;
    }
    @media (max-width: 767px) {
      .copy-error-message {
        font-size: 10px !important;
        padding: 12px !important;
      }
      .copy-error-message button {
        font-size: 10px !important;
        padding: 6px 12px !important;
      }
    }
  </style>
  <script>
    function showTab(tabId) {
      document.querySelectorAll('.tab-content').forEach(function(tab) {
        tab.classList.remove('active');
      });
      document.querySelectorAll('.tab').forEach(function(tab) {
        tab.setAttribute("aria-selected", "false");
      });
      document.getElementById(tabId).classList.add('active');
      document.getElementById("tab-" + tabId).setAttribute("aria-selected", "true");
    }
    function filterByDay() {
      var selectedDay = document.getElementById("dayFilter").value;
      var selectedGroup = document.getElementById("groupFilter").value;
      var days = document.querySelectorAll(".day");
      var movieGroups = document.querySelectorAll(".movie-group");
      if (selectedGroup === "by-day") {
        days.forEach(function(day) {
          if (selectedDay === "all" || day.getAttribute("data-date") === selectedDay) {
            day.style.display = "";
          } else {
            day.style.display = "none";
          }
        });
        movieGroups.forEach(function(group) {
          group.style.display = "none";
        });
      } else if (selectedGroup === "by-movie") {
        days.forEach(function(day) {
          day.style.display = "none";
        });
        movieGroups.forEach(function(group) {
          group.style.display = "";
        });
      }
    }
    // Copy the shareable link (with hash) to clipboard and show temporary feedback.
    function copyLink(movieId) {
      var url = window.location.href.split('#')[0] + '#' + movieId;
      navigator.clipboard.writeText(url).then(function() {
        var shareLink = document.getElementById("share-" + movieId);
        if (shareLink) {
          var originalContent = shareLink.innerHTML;
          shareLink.innerHTML = "Copied!";
          setTimeout(function() {
            shareLink.innerHTML = "🔗";
          }, 2000);
        }
      }, function() {
        alert("Failed to copy link.");
      });
    }
    // On page load, if a hash is present, scroll to that movie and highlight it.
    document.addEventListener("DOMContentLoaded", function() {
      if (window.location.hash) {
        var target = document.getElementById(window.location.hash.substring(1));
        if (target) {
          setTimeout(function() {
            target.scrollIntoView({ behavior: "smooth", block: "center" });
            target.classList.add("highlight");
            setTimeout(function() {
              target.classList.remove("highlight");
            }, 3000);
          }, 100);
        }
      }
    });
    // New JavaScript for the glitch button and dialog
    let clickCount = 0;
    function handleGlitchButtonClick() {
      clickCount++;
      document.body.classList.add('glitch');
      setTimeout(() => {
        document.body.classList.remove('glitch');
      }, 300);
      if (clickCount === 3) {
        window.location.href = 'truth.html';
      } else {
        document.getElementById('glitchDialog').style.display = 'block';
      }
    }
    function closeDialog() {
      document.getElementById('glitchDialog').style.display = 'none';
    }
    let allShowtimes = {};
    function showOtherTimes(title, currentTime, currentDate, currentCinema, currentId) {
      let dialog = document.getElementById('otherTimesDialog');
      let list = '';
      let found = false;
      let seenShowtimes = new Set(); // Track unique showtimes

      if (allShowtimes[title]) {
        // Sort showtimes by date and time using formatted datetime
        allShowtimes[title].sort((a, b) => {
          // Use formatted datetime for proper chronological sorting
          return a.formatted_datetime.localeCompare(b.formatted_datetime);
        });

        allShowtimes[title].forEach(function(st) {
          // Create a unique key for this showtime
          const showtimeKey = `${st.time}-${st.date}-${st.cinema}`;
          
          // Only show if we haven't seen this exact showtime before and it's not the current one
          if (!seenShowtimes.has(showtimeKey) && 
              !(st.time === currentTime && st.date === currentDate && st.cinema === currentCinema)) {
            seenShowtimes.add(showtimeKey);
            let targetId = st.id ? st.id : '';
            // Ensure we always have a date
            const displayDate = st.date || 'Unknown Date';
            list += `<a class='other-times-link' href='#${targetId}' onclick="closeOtherTimesDialog(); setTimeout(function(){document.getElementById('${targetId}').scrollIntoView({behavior:'smooth',block:'center'});}, 100);">${displayDate} — ${st.time} @ ${st.cinema}</a>`;
            found = true;
          }
        });
      }
      if (!found) {
        list = '<div>No other showtimes for this movie.</div>';
      }
      dialog.querySelector('.other-times-list').innerHTML = list;
      dialog.querySelector('.other-times-dialog-title').innerText = `Other Showtimes for: ${title}`;
      dialog.style.display = 'block';
    }
    function closeOtherTimesDialog() {
      document.getElementById('otherTimesDialog').style.display = 'none';
    }
    document.addEventListener('DOMContentLoaded', function() {
      // Build allShowtimes from data attributes, using a Set to track unique showtimes
      let seenShowtimes = new Set();
      document.querySelectorAll('[data-movie-title]').forEach(function(el) {
        let title = el.getAttribute('data-movie-title');
        let time = el.getAttribute('data-movie-time');
        let date = el.getAttribute('data-movie-date');
        let cinema = el.getAttribute('data-movie-cinema');
        let formatted_datetime = el.getAttribute('data-formatted-datetime') || '';
        let id = el.getAttribute('id');
        
        // Ensure we have all required data
        if (!title || !time || !date || !cinema) {
          console.warn('Missing data for showtime:', {title, time, date, cinema});
          return;
        }
        
        // Create a unique key for this showtime
        const showtimeKey = `${title}|${time}|${date}|${cinema}`;
        
        // Only add if we haven't seen this exact showtime before
        if (!seenShowtimes.has(showtimeKey)) {
          seenShowtimes.add(showtimeKey);
          if (!allShowtimes[title]) allShowtimes[title] = [];
          allShowtimes[title].push({time, date, cinema, id, formatted_datetime});
        }
      });
    });
    function copyShareLink(movieId, event) {
      event.preventDefault();
      event.stopPropagation();
      
      // Create the shareable URL
      const url = window.location.href.split('#')[0] + '#' + movieId;
      const btn = event.currentTarget;
      const originalText = btn.innerHTML;
      
      // Fallback method for copying
      function fallbackCopyToClipboard(text) {
        const textArea = document.createElement('textarea');
        textArea.value = text;
        
        // Make the textarea out of viewport
        textArea.style.position = 'fixed';
        textArea.style.left = '-999999px';
        textArea.style.top = '-999999px';
        document.body.appendChild(textArea);
        textArea.focus();
        textArea.select();
        
        let successful = false;
        try {
          successful = document.execCommand('copy');
        } catch (err) {
          console.error('Fallback copy failed:', err);
        }
        
        document.body.removeChild(textArea);
        return successful;
      }
      
      // Try modern clipboard API first, then fallback
      if (navigator.clipboard && window.isSecureContext) {
        navigator.clipboard.writeText(url)
          .then(() => {
            showCopySuccess(btn, originalText);
          })
          .catch(() => {
            // If clipboard API fails, try fallback
            if (fallbackCopyToClipboard(url)) {
              showCopySuccess(btn, originalText);
            } else {
              showCopyError(btn, originalText);
            }
          });
      } else {
        // Try fallback for non-secure contexts
        if (fallbackCopyToClipboard(url)) {
          showCopySuccess(btn, originalText);
        } else {
          showCopyError(btn, originalText);
        }
      }
    }
    
    function showCopySuccess(btn, originalText) {
      btn.innerHTML = '✓';
      btn.classList.add('copied');
      
      // Reset after 2 seconds
      setTimeout(() => {
        btn.innerHTML = originalText;
        btn.classList.remove('copied');
      }, 2000);
    }
    
    function showCopyError(btn, originalText) {
      btn.innerHTML = '❌';
      btn.classList.add('error');
      
      // Show a more helpful error message
      const errorMsg = document.createElement('div');
      errorMsg.className = 'copy-error-message';
      errorMsg.textContent = 'Click to copy manually: ' + window.location.href.split('#')[0] + '#' + btn.closest('.movie').id;
      errorMsg.style.cssText = `
        position: fixed;
        top: 50%;
        left: 50%;
        transform: translate(-50%, -50%);
        background: #111;
        border: 2px solid #ff0080;
        padding: 16px;
        color: #39ff14;
        font-family: 'Press Start 2P', cursive;
        font-size: 12px;
        text-align: center;
        box-shadow: 0 0 24px #00fff7;
        z-index: 2000;
        max-width: 90%;
        word-break: break-all;
      `;
      
      // Add close button
      const closeBtn = document.createElement('button');
      closeBtn.textContent = 'Close';
      closeBtn.style.cssText = `
        margin-top: 12px;
        padding: 8px 16px;
        background: #ff0080;
        color: #fff;
        border: none;
        border-radius: 0;
        font-family: 'Press Start 2P', cursive;
        font-size: 12px;
        cursor: pointer;
        box-shadow: 0 0 8px #00fff7;
      `;
      closeBtn.onclick = () => {
        document.body.removeChild(errorMsg);
        btn.innerHTML = originalText;
        btn.classList.remove('error');
      };
      
      errorMsg.appendChild(closeBtn);
      document.body.appendChild(errorMsg);
      
      // Reset button after 2 seconds if error message is closed
      setTimeout(() => {
        if (document.body.contains(errorMsg)) {
          document.body.removeChild(errorMsg);
        }
        btn.innerHTML = originalText;
        btn.classList.remove('error');
      }, 10000); // Auto-close after 10 seconds
    }
  </script>
</head>
<body>
  <div class="container">
    <h1>Carolina Theatre Schedule</h1>
    <div class="tabs" role="tablist">
      <div id="tab-schedule" class="tab" role="tab" tabindex="0" onclick="showTab('schedule')" aria-selected="true">Movie Schedule</div>
      <div id="tab-daily-cinema" class="tab" role="tab" tabindex="0" onclick="showTab('daily-cinema')" aria-selected="false">The Daily Cinema Club</div>
      <div id="tab-about" class="tab" role="tab" tabindex="0" onclick="showTab('about')" aria-selected="false">Why This Exists</div>
    </div>
    <div id="otherTimesDialog" class="other-times-dialog">
      <div class='other-times-dialog-title'></div>
      <div class="other-times-list"></div>
      <button onclick="closeOtherTimesDialog()">Close</button>
    </div>
    <!-- Movie Schedule Tab -->
    <div id="schedule" class="tab-content active" role="tabpanel">
      <div class="filter">
        <label for="groupFilter">Group By:</label>
        <select id="groupFilter" onchange="filterByDay()" aria-label="Group movies by day or movie">
          <option value="by-day">By Day</option>
          <option value="by-movie">By Movie</option>
        </select>
        <label for="dayFilter">Filter by Day:</label>
        <select id="dayFilter" onchange="filterByDay()" aria-label="Filter movies by day">
          <option value="all">All Days</option>
"""
    
    # Populate filter dropdown for movie schedule.
    for date in sorted_dates:
        html_content += f"          <option value=\"{date}\">{date}</option>\n"
    html_content += """        </select>
      </div>
"""
    
    # Output movies grouped by day (as before) and also grouped by movie (new).
    movie_counter = 1
    for date in sorted_dates:
        html_content += f"      <div class='day' data-date='{date}'>\n"
        html_content += f"        <h2>{date}</h2>\n"
        for movie in schedule_showtimes_by_date[date]:
            # Create a unique movie ID based on the title slug and counter.
            movie_slug = slugify(movie['title'])
            movie_id = f"movie-{movie_slug}-{movie_counter}"
            formatted_datetime = movie.get('formatted_datetime', '')
            html_content += (
                "        <div class='movie' id='" + movie_id + "' data-movie-title='" + movie['title'] + "' data-movie-time='" + movie['time'] + "' data-movie-date='" + date + "' data-movie-cinema='" + movie['cinema'] + "' data-formatted-datetime='" + formatted_datetime + "'>"
                f"<span class='movie-title'><a href='{movie['link']}' target='_blank'>{movie['title']}</a>"
                f"<button class='share-btn' onclick='copyShareLink(\"{movie_id}\", event)' title='Copy shareable link'>🔗</button></span> "
                "<div class='movie-info'>"
                f"<span class='movie-time'>{movie['time']}</span> "
                f"<span class='movie-cinema'>{movie['cinema']}</span>"
                f"<button class='other-times-btn' onclick=\"showOtherTimes('{movie['title']}', '{movie['time']}', '{date}', '{movie['cinema']}', '{movie_id}')\">Show Other Times</button>"
                "</div></div>\n"
            )
            movie_counter += 1
        html_content += "      </div>\n"
    
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
        html_content += f"      <div class='movie-group' style='display:none;'>\n"
        html_content += f"        <h3>{title}</h3>\n"
        for movie in movies:
            movie_slug = slugify(movie['title'])
            movie_id = f"movie-{movie_slug}-{movie_counter}"
            # Append the day (date) (e.g. "(Fri, Feb 28)") so that the user can see on which day the movie is playing.
            day_str = movie.get("display_date", "").strip()
            formatted_datetime = movie.get('formatted_datetime', '')
            html_content += (
                "        <div class='movie' id='" + movie_id + "' data-movie-title='" + movie['title'] + "' data-movie-time='" + movie['time'] + "' data-movie-date='" + day_str + "' data-movie-cinema='" + movie['cinema'] + "' data-formatted-datetime='" + formatted_datetime + "'>"
                f"<span class='movie-title'><a href='{movie['link']}' target='_blank'>{movie['title']}</a>"
                f"<button class='share-btn' onclick='copyShareLink(\"{movie_id}\", event)' title='Copy shareable link'>🔗</button></span> "
                "<div class='movie-info'>"
                f"<span class='movie-time'>{movie['time']} ({day_str})</span> "
                f"<span class='movie-cinema'>{movie['cinema']}</span>"
                f"<button class='other-times-btn' onclick=\"showOtherTimes('{movie['title']}', '{movie['time']}', '{day_str}', '{movie['cinema']}', '{movie_id}')\">Show Other Times</button>"
                "</div></div>\n"
            )
            movie_counter += 1
        html_content += "      </div>\n"
    html_content += "    </div>\n"
    
    # The Daily Cinema Club Tab Content (updated text and centered layout)
    html_content += """    <div id="daily-cinema" class="tab-content" role="tabpanel">
      <div class="block richText">
        <h2 class="gela">The Daily Cinema Club</h2><br>
        <strong><a href="https://www.thedailybeerbar.com/about/events" target="_blank">The Daily's Event Page</a></strong></br>
        <p>6 PM | <strong>Retro Reels: A VHS Cinema Club</strong></p>
        <p>Calling all movie buffs, nostalgia lovers, and tape-heads! Experience a journey back in time as the clock is rolled back and the VCR dusted off to showcase cinema's greatest gems.</p>
        <p>Every Tuesday night, catch an old-school VHS screening paired with the ultimate classic combo: <br> <strong>Miller High Life &amp; Popcorn</strong>.</p>
        <hr>
        <h3>Upcoming Screenings</h3>
        <ul>
          <li><strong>Previously (Tuesday, 03/18):</strong> Pocahontas (1995 film)</li>
          <li><strong>Next Up (Tuesday, 03/25):</strong> TBD!</li>
        </ul>
        <hr>
        <p>Grab a drink, claim a seat, and enjoy a nostalgic rewind!</p>
        <pre>
         o               ||   \\===
          \\              ||^^^^^^^
           \\      /\\     ||   ^^^
            \\    /  o    |'-------
             \\__/        '--------
     _______ /  \\_________     
    | __________________  |     
    ||"'`':`.,~"`;"`;#'~|_|     
    ||";";.,`~;`'+.:',!`|O|     
    ||.;',`'`.,`':.`~,;'|O|     
    ||':'""`~`"'`'`::'`'|o|    '
    ||.:',~;~'`;'`.,:'`;|_|  ' @
    ||-'`:'`.`;.:""\";/;`| |  @ |
    ||'`'`~';?;`:`.,`.:'| |  | |
    |'------------------' | '---'
----'---------------------'--\\_/--
        </pre>
      </div>
    </div>
"""
    # "Why This Exists" Tab Content
    html_content += """    <div id="about" class="tab-content" role="tabpanel">
      <h2>Why This Exists</h2>
      <p>Let's be honest—the official Carolina Theatre website is a maze of frustration, a test of patience for even the most devoted cinephile. Want to know what's playing? Good luck. Instead of a simple list, you're forced to navigate finicky carousels, decipher cryptic categorizations, and dig through layers of unnecessary clicks just to find a showtime.</p>
      
      <p>Rather than endure yet another round of digital torment, this site was built—a clean, fast, no-nonsense listing of what's actually playing.<br>
      The list isn't manually curated; it's powered by a dedicated backend script that tirelessly gathers and organizes showtimes with precision. The result? A constantly up-to-date, frustration-free experience delivered straight to you.<br><br>
      No fluff, no distractions—just movies and their showtimes. Because all deserve better.<br></p>
      
      <p><em>~Forged with noble wrath and unwavering purpose~</em><br>Built by Andrew Evans aka lilcrisp</p>
      
      <pre>
               __             ___
      // )    ___--""    "-.
 \\ |,"( /`--""              `.  
  \\/ o                        \\  
  (   _.-.              ,'"    ;  
   |\\"   /`. \\  ,      /       | 
   | \\  ' .'`.; |      |       \\ 
   |  '-'.'    |  --..,,,\\_    \\_______      
   |       _.-'        ___"-   )      \\\"\\\"\\--.  
    \\____-"           '''---~""         
      </pre>
      <p>This little rat lives in the backend tirelessly gathering and organizing the movie showtimes for you.</p>
      <button class="glitch-button" onclick="handleGlitchButtonClick()">DO NOT CLICK THIS BUTTON</button>
    </div>
"""
    # Hidden dialogs
    html_content += """    <div id="glitchDialog" class="dialog">
      <p>System Error...</p>
      <p>Reality Corrupted</p>
      <button onclick="closeDialog()">Close</button>
    </div>
"""
    # Footer
    html_content += """    <footer>
      <p>"I wish it need not have happened in my time," said Frodo.<br>
      "So do I," said Gandalf, "and so do all who live to see such times. But that is not for them to decide. 
      All we have to decide is what to do with the time that is given us." – J.R.R. Tolkien</p>
    </footer>
    <button class="glitch-button" onclick="handleGlitchButtonClick()">DO NOT CLICK THIS BUTTON</button>
  </div>
</body>
</html>"""
    
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
    
    # Allow user to specify output file as command line argument
    output_file = None
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
        print(f"Using custom output file: {output_file}")
    
    print("Generating Carolina Theatre website from database...")
    success = generate_html(DB_NAME, output_file)
    
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