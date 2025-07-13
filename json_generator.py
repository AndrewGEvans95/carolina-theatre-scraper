import sqlite3
import json
import os
from datetime import datetime

def get_showtimes_from_database(db_name="movie_showtimes.db"):
    """
    Retrieve showtimes from the database and return them as structured data.
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
            
            showtimes.append({
                "title": title,
                "date": original_date,
                "time": original_time,
                "formatted_datetime": formatted_datetime,
                "cinema": cinema,
                "link": link
            })
        
        return showtimes
        
    except sqlite3.Error as e:
        print(f"Database error: {e}")
        return []
    except Exception as e:
        print(f"Error reading from database: {e}")
        return []

def generate_json(db_name="movie_showtimes.db", output_file="carolina-theatre-astro/src/data/showtimes.json"):
    """
    Generate JSON file from database for Astro to consume.
    """
    print("Reading showtimes from database...")
    showtimes_data = get_showtimes_from_database(db_name)
    
    if not showtimes_data:
        print("No showtimes found in database")
        return False
    
    print(f"Found {len(showtimes_data)} showtimes in database")
    
    # Ensure output directory exists
    output_dir = os.path.dirname(output_file)
    os.makedirs(output_dir, exist_ok=True)
    
    # Generate metadata
    data = {
        "generated_at": datetime.now().isoformat(),
        "total_showtimes": len(showtimes_data),
        "showtimes": showtimes_data
    }
    
    # Write JSON file
    try:
        with open(output_file, "w", encoding="utf-8") as file:
            json.dump(data, file, indent=2, ensure_ascii=False)
        print(f"JSON file successfully saved to: {output_file}")
        return True
    except Exception as e:
        print(f"Error writing JSON file: {str(e)}")
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
    output_file = "carolina-theatre-astro/src/data/showtimes.json"
    if len(sys.argv) > 1:
        output_file = sys.argv[1]
        print(f"Using custom output file: {output_file}")
    
    print("Generating JSON data for Astro...")
    success = generate_json(DB_NAME, output_file)
    
    if not success:
        print("\nFailed to generate JSON data")
        exit(1)
    
    print("JSON data successfully generated for Astro!")